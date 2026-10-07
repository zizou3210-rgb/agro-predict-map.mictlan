from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from ce_pipeline.phase03 import script03
from pipeline.progress import ProgressReporter
from preprocess import soil_enrichment
import shared_cache


def soil_record(source="soilgrids"):
    return soil_enrichment.build_soil_record(
        sand_gkg=400, silt_gkg=400, clay_gkg=200,
        depth_to_bedrock_cm=75, source=source,
    )


def rows(count):
    return [{soil_enrichment.LAT_HEADER: 1 + index / 1000,
             soil_enrichment.LON_HEADER: 32, "row": index} for index in range(count)]


class SoilProgressTest(unittest.TestCase):
    def setUp(self):
        provider = patch.dict(os.environ, {"APP_PHASE03_SOIL_PROVIDER": "rest"})
        provider.start()
        self.addCleanup(provider.stop)

    def test_isric_request_quota_waits_without_real_sleep(self):
        clock = [0.0]
        with patch.object(soil_enrichment, "_SOILGRIDS_REQUEST_TIMES", deque()), patch.object(
            soil_enrichment.time, "monotonic", side_effect=lambda: clock[0],
        ), patch.object(soil_enrichment.time, "sleep", side_effect=lambda delay: clock.__setitem__(0, clock[0] + delay)) as sleep:
            for _ in range(6):
                soil_enrichment._wait_for_soilgrids_slot("https://rest.isric.org/soilgrids/v2.0/properties/query")
            self.assertEqual(sleep.call_count, 1)
            self.assertEqual(clock[0], 60)
            soil_enrichment._wait_for_soilgrids_slot("http://localhost:8000/soil")
            self.assertEqual(sleep.call_count, 1)

    def test_workers_query_concurrently_and_pending_queue_is_bounded(self):
        barrier = threading.Barrier(2, timeout=2)
        gate_lock = threading.Lock()
        calls = []
        executors = []

        def resolve(latitude, longitude, *, payload, lookup_shared_cache):
            self.assertFalse(lookup_shared_cache)
            with gate_lock:
                calls.append(latitude)
                first_pair = len(calls) <= 2
            if first_pair:
                barrier.wait()  # Fails if a payload lock serializes the network.
            return soil_record(), "soilgrids", True

        class TrackingExecutor(ThreadPoolExecutor):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.tracking_lock = threading.RLock()
                self.outstanding = self.maximum = 0
                executors.append(self)

            def submit(self, *args, **kwargs):
                with self.tracking_lock:
                    self.outstanding += 1
                    self.maximum = max(self.maximum, self.outstanding)
                    future = super().submit(*args, **kwargs)
                    future.add_done_callback(self.finished)
                    return future

            def finished(self, future):
                with self.tracking_lock:
                    self.outstanding -= 1

        progress = []
        persisted = {}
        with tempfile.TemporaryDirectory() as directory, patch.object(
            script03, "resolve_phase03_soil_worker_limit", return_value=2,
        ), patch.object(script03, "ThreadPoolExecutor", TrackingExecutor), patch.object(
            soil_enrichment, "get_soil_cache_entries", return_value={},
        ), patch.object(soil_enrichment, "upsert_soil_cache_entries", side_effect=lambda batch: persisted.update(batch)), patch.object(
            soil_enrichment, "resolve_soil_record_from_payload", side_effect=resolve,
        ):
            source = rows(80)
            source.insert(1, dict(source[0]))
            enriched, metadata = script03.enrich_soils(
                source, Path(directory) / "soil.json",
                progress_callback=lambda *event: progress.append(event),
            )
            saved = json.loads((Path(directory) / "soil.json").read_text())
        self.assertEqual(len(calls), 80)
        self.assertEqual(len(enriched), 81)
        self.assertEqual([record["row"] for record in enriched], [record["row"] for record in source])
        self.assertEqual(len(saved["points"]), 80)
        self.assertEqual(len(persisted), 80)
        self.assertEqual(metadata["soil_persisted_points"], 80)
        self.assertLessEqual(executors[0].maximum, 4)
        self.assertEqual(progress[-1][3]["stage_percent"], 100)
        self.assertEqual(progress[-1][3]["soil_processed_rows"], 81)
        self.assertTrue(all(event[3].get("soil_pending_tasks", 0) <= 4 for event in progress))

    def test_confirmed_results_survive_another_worker_failure(self):
        confirmed = threading.Event()
        persisted = {}

        def persist(batch):
            persisted.update(batch)
            confirmed.set()

        def resolve(latitude, longitude, **kwargs):
            if latitude >= 1.064:
                self.assertTrue(confirmed.wait(2))
                raise RuntimeError("injected failure")
            return soil_record(), "soilgrids", True

        with tempfile.TemporaryDirectory() as directory, patch.object(
            script03, "resolve_phase03_soil_worker_limit", return_value=1,
        ), patch.object(soil_enrichment, "get_soil_cache_entries", return_value={}), patch.object(
            soil_enrichment, "upsert_soil_cache_entries", side_effect=persist,
        ), patch.object(soil_enrichment, "resolve_soil_record_from_payload", side_effect=resolve):
            path = Path(directory) / "soil.json"
            with self.assertRaisesRegex(RuntimeError, "injected failure"):
                script03.enrich_soils(rows(65), path)
            saved = json.loads(path.read_text())
        self.assertEqual(len(saved["points"]), 64)
        self.assertEqual(len(persisted), 64)

    def test_shared_cache_hit_avoids_service_and_preserves_fallback_provenance(self):
        point_id = soil_enrichment.cache_key(1, 32)
        cached = soil_record("fallback_default")
        with tempfile.TemporaryDirectory() as directory, patch.object(
            soil_enrichment, "get_soil_cache_entries", return_value={point_id: cached},
        ), patch.object(soil_enrichment, "resolve_soil_record_from_payload", side_effect=AssertionError("no network")), patch.object(
            soil_enrichment, "upsert_soil_cache_entries", side_effect=AssertionError("no new samples"),
        ):
            enriched, metadata = script03.enrich_soils(rows(1), Path(directory) / "soil.json")
        self.assertEqual(metadata["soil_cache_hits"], 1)
        self.assertEqual(metadata["soil_fallback_cells"], 1)
        self.assertEqual(enriched[0]["soil_source"], "fallback_default")

    def test_batched_shared_lookup_reads_more_than_one_sqlite_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "cache.sqlite3"
            entries = {str(index): soil_record() for index in range(805)}
            with patch.object(shared_cache, "_resolve_legacy_soil_cache_path", return_value=Path(directory) / "absent.json"):
                shared_cache.upsert_soil_cache_entries(entries, db_path=database)
                loaded = shared_cache.get_soil_cache_entries([*entries, "missing", "0"], db_path=database)
        self.assertEqual(loaded, entries)


class ProgressReporterTest(unittest.TestCase):
    def test_new_reporter_recovers_persisted_stage_history(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "progress.json"
            first = ProgressReporter(path)
            first.update(50, "Computing windows", "Calculating")
            first.pause(52, "Validation", "Waiting")
            first.close()
            second = ProgressReporter(path)
            try:
                second.update(56, "Prediction", "Continuing")
                snapshot = json.loads(path.read_text())
                self.assertEqual([event["stage"] for event in snapshot["activity"]], ["Computing windows", "Validation", "Prediction"])
                self.assertEqual(snapshot["sequence"], 3)
            finally:
                second.close()

    def test_heartbeat_preserves_counters_and_terminal_state_stops_it(self):
        signal = threading.Event()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "progress.json"
            reporter = ProgressReporter(path, heartbeat_seconds=0.01)
            original_write = reporter._write

            def write(payload):
                original_write(payload)
                if payload["sequence"] >= 2:
                    signal.set()

            try:
                with patch.object(reporter, "_write", side_effect=write):
                    reporter.update(50, "Saving workbook", "Writing rows", details={"stage_completed": 3, "stage_total": 10})
                    self.assertTrue(signal.wait(2))
                snapshot = json.loads(path.read_text())
                self.assertEqual(snapshot["details"]["stage_completed"], 3)
                self.assertEqual(snapshot["stage"], "Saving workbook")
                self.assertGreaterEqual(snapshot["sequence"], 2)
                reporter.complete("ready")
                self.assertFalse(reporter._thread.is_alive())
                self.assertEqual(json.loads(path.read_text())["status"], "completed")
            finally:
                reporter.close()

    def test_concurrent_updates_remain_readable_and_history_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "progress.json"
            reporter = ProgressReporter(path, heartbeat_seconds=60)
            try:
                reporter.update(1, "Preparing", "Start")

                def update(index):
                    reporter.update(index, f"Stage {index}", "Processing")
                    self.assertIsInstance(json.loads(path.read_text()), dict)

                with ThreadPoolExecutor(max_workers=4) as executor:
                    list(executor.map(update, range(220)))
                snapshot = json.loads(path.read_text())
                self.assertEqual(len(snapshot["activity"]), 200)
                self.assertTrue(all(event.get("ended_at") for event in snapshot["activity"][:-1]))
            finally:
                reporter.close()


if __name__ == "__main__":
    unittest.main()
