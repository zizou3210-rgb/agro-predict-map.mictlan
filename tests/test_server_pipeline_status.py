from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import server

from server import AppRequestHandler


class PipelineStatusTest(unittest.TestCase):
    def test_cancel_all_includes_processes_recovered_after_server_restart(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            server, "terminate_existing_pipeline_processes", return_value=2,
        ) as cancel, patch.object(server, "get_active_featurehero_jobs", return_value={}), patch.object(
            server, "FEATUREHERO_JOBS_FILE", Path(directory) / "jobs.json",
        ):
            handler = object.__new__(AppRequestHandler)
            handler.send_json = Mock()
            handler.handle_cancel_all_processes()
            cancel.assert_called_once()
            self.assertEqual(handler.send_json.call_args.args[0]["cancelled_pipeline_jobs"], 2)

    def test_orphan_cancellation_marks_its_run_and_ignores_non_python_commands(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "job"
            pipeline = str((server.APP_DIR / "pipeline" / "run_pipeline.py").resolve())
            listing = Mock(stdout=f"99999991 /usr/bin/python {pipeline} --run-dir {run_dir}\n99999992 echo {pipeline}\n")
            with patch.object(server, "PIPELINE_RUNS_DIR", Path(directory)), patch.dict(
                server.PIPELINE_JOBS, {}, clear=True,
            ), patch.object(server, "reap_finished_pipeline_jobs"), patch.object(
                server.subprocess, "run", return_value=listing,
            ), patch.object(server, "terminate_pid", return_value=True) as kill, patch.object(
                server, "_write_pipeline_progress_status",
            ) as mark:
                self.assertEqual(server.terminate_existing_pipeline_processes(), 1)
                kill.assert_called_once_with(99999991)
                self.assertEqual(mark.call_args.kwargs["status"], "cancelled")
                self.assertEqual(mark.call_args.args[0], run_dir)

    def test_cancelled_recovered_job_does_not_try_to_build_completed_result(self):
        handler = object.__new__(AppRequestHandler)
        handler.send_json = Mock()
        handler.finalize_job = Mock(return_value=(
            0, {"status": "cancelled"},
            {"run_dir": "/tmp/pipeline-status-test", "source_name": "input.xlsx"},
        ))
        handler.build_completed_payload = Mock(side_effect=AssertionError("Cancelled job has no completed result"))
        handler.handle_process_status("job-test")
        self.assertEqual(handler.send_json.call_args.args[0]["status"], "cancelled")
        handler.build_completed_payload.assert_not_called()

    def test_completion_marker_while_process_is_running_keeps_client_polling(self):
        handler = object.__new__(AppRequestHandler)
        handler.send_json = Mock()
        handler.finalize_job = Mock(return_value=(
            None,
            {"status": "completed", "percent": 100},
            {"run_dir": "/tmp/pipeline-status-test", "source_name": "input.xlsx"},
        ))
        with patch("server.should_skip_running_preprocess_geojson", return_value=True):
            handler.handle_process_status("job-test")

        payload = handler.send_json.call_args.args[0]
        self.assertEqual(payload["status"], "running")
        self.assertEqual(payload["progress"]["status"], "running")

    def test_transient_result_read_failure_does_not_publish_empty_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            (run_dir / "progress.json").write_text(json.dumps({
                "status": "completed", "percent": 100,
            }))
            handler = object.__new__(AppRequestHandler)
            handler.send_json = Mock()
            handler.finalize_job = Mock(return_value=(
                0,
                {"status": "completed", "percent": 100},
                {"run_dir": directory, "source_name": "input.xlsx"},
            ))
            handler.build_completed_payload = Mock(side_effect=OSError("temporary read failure"))
            with patch.dict("server.PIPELINE_JOBS", {"job-test": {"run_dir": directory}}):
                handler.handle_process_status("job-test")

            payload = handler.send_json.call_args.args[0]
            self.assertEqual(payload["status"], "running")
            self.assertEqual(payload["progress"]["status"], "running")
            self.assertIn("warning", payload)

    def test_completed_response_contains_result_artifacts(self):
        handler = object.__new__(AppRequestHandler)
        handler.send_json = Mock()
        handler.finalize_job = Mock(return_value=(
            0,
            {"status": "completed", "percent": 100},
            {"run_dir": "/tmp/pipeline-status-test", "source_name": "input.xlsx"},
        ))
        handler.build_completed_payload = Mock(return_value={
            "geojson_download_url": "/api/process-xlsx/artifact/job-test/display_geojson",
        })
        with patch("server.cleanup_completed_pipeline_run_temporary_artifacts"):
            handler.handle_process_status("job-test")

        payload = handler.send_json.call_args.args[0]
        self.assertEqual(payload["status"], "completed")
        self.assertTrue(payload["geojson_download_url"])


if __name__ == "__main__":
    unittest.main()
