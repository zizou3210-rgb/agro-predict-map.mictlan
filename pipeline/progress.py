from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, RLock, Thread
from typing import Any


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProgressReporter:
    """Publish coherent snapshots, bounded stage history and activity heartbeats."""

    def __init__(self, progress_file: Path | None, *, heartbeat_seconds: float = 5):
        self.progress_file = progress_file
        self._lock = RLock()
        self._stop = Event()
        self._thread = None
        self._heartbeat_seconds = heartbeat_seconds
        self._payload = {}
        self._history = []
        self._sequence = 0
        self._stage_started_at = time.monotonic()
        if progress_file is not None:
            try:
                previous = json.loads(progress_file.read_text(encoding="utf-8"))
                if isinstance(previous, dict):
                    self._payload = previous
                    history = previous.get("activity", [])
                    if isinstance(history, list):
                        self._history = [event for event in history if isinstance(event, dict)][-200:]
                    self._sequence = int(previous.get("sequence", 0) or 0)
            except (OSError, ValueError, TypeError):
                pass

    def _write(self, payload: dict[str, Any]) -> None:
        if self.progress_file is None:
            return
        self.progress_file.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.progress_file.parent, delete=False) as temporary:
            json.dump(payload, temporary, ensure_ascii=False)
            temporary_path = Path(temporary.name)
        try:
            os.replace(temporary_path, self.progress_file)
        finally:
            temporary_path.unlink(missing_ok=True)

    def _publish(self):
        self._sequence += 1
        self._payload.update(
            updated_at=utc_timestamp(), sequence=self._sequence,
            stage_elapsed_seconds=round(time.monotonic() - self._stage_started_at, 1),
            activity=list(self._history),
        )
        self._write(self._payload)

    def _heartbeat(self):
        while not self._stop.wait(self._heartbeat_seconds):
            with self._lock:
                if self._payload.get("status") != "running":
                    continue
                try:
                    self._publish()
                except OSError:
                    # An explicit update will still surface persistence errors.
                    pass

    def update(self, percent, stage: str, message: str, *, status="running", details=None):
        with self._lock:
            if self._payload.get("stage") != stage or self._payload.get("status") != status:
                timestamp = utc_timestamp()
                if self._history:
                    previous_status = self._history[-1].get("status")
                    if previous_status == "running":
                        previous_status = status if status in {"error", "cancelled"} else "finished"
                    self._history[-1] = {**self._history[-1], "ended_at": timestamp,
                        "status": previous_status,
                    }
                self._history.append({"stage": stage, "message": message, "status": status, "started_at": timestamp})
                self._history = self._history[-200:]
                self._stage_started_at = time.monotonic()
            self._payload = {"status": status, "percent": percent, "stage": stage, "message": message}
            if details:
                self._payload["details"] = dict(details)
            if self._history:
                event_details = dict(details or {})
                self._history[-1].update(message=message)
                self._history[-1]["details"] = event_details
                if event_details.get("stage_percent") == 100:
                    self._history[-1].update(status="finished", ended_at=utc_timestamp())
            self._publish()
            if status == "running" and self.progress_file is not None and self._thread is None:
                self._thread = Thread(target=self._heartbeat, name="pipeline-progress", daemon=True)
                self._thread.start()

    def close(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)

    def complete(self, message: str, *, details=None):
        self.update(100, "Upload complete", message, status="completed", details=details)
        self.close()

    def error(self, message: str, *, details=None):
        self.update(100, "Upload error", message, status="error", details=details)
        self.close()

    def pause(self, percent, stage: str, message: str, *, details=None):
        self.update(percent, stage, message, status="paused", details=details)


def work_progress(callback, percent, stage, *, phase, unit="rows"):
    """Throttle measured work updates; reserve completion for successful finalization."""
    started = time.monotonic()
    last = None

    def report(completed, total, finished=False):
        nonlocal last
        now = time.monotonic()
        if callback is None or (last is not None and not finished and now - last < 1):
            return
        last = now
        elapsed = now - started
        rate = completed / elapsed if elapsed else 0
        callback(percent, stage, f"{completed:,}/{total:,} {unit} processed." if not finished else f"Completed {total:,} {unit}.", {
            "phase": phase, "stage_completed": completed, "stage_total": total,
            "stage_unit": unit,
            "stage_percent": 100 if finished else min(99, completed / total * 100) if total else 0,
            "stage_elapsed_seconds": round(elapsed, 1),
            "stage_rate_per_second": round(rate, 3),
            "stage_eta_seconds": round((total - completed) / rate, 1) if rate and completed < total else None,
        })
    return report


def write_dataframe_excel(df, output_file, progress_callback=None):
    if progress_callback is None:
        return df.to_excel(output_file, index=False)
    import pandas as pd
    from pandas.io.formats.excel import ExcelFormatter

    total = df.size + len(df.columns)
    progress_callback(0, total)

    class ReportingFormatter(ExcelFormatter):
        def get_formatted_cells(self):
            for completed, cell in enumerate(super().get_formatted_cells(), 1):
                yield cell
                progress_callback(completed, total)

    with pd.ExcelWriter(output_file) as writer:
        ReportingFormatter(df, index=False).write(writer, sheet_name="Sheet1")
    progress_callback(total, total, True)


def reported_operation(callback, percent, stage, phase, operation):
    report = work_progress(callback, percent, stage, phase=phase, unit="steps")
    report(0, 1)
    result = operation()
    report(1, 1, True)
    return result


def write_dataframe_csv(df, output_file, progress_callback=None):
    if progress_callback is None:
        return df.to_csv(output_file, index=False)
    total = len(df)
    progress_callback(0, total)
    with open(output_file, "w", encoding="utf-8", newline="") as handle:
        if not total:
            df.to_csv(handle, index=False)
        for start in range(0, total, 10000):
            df.iloc[start:start + 10000].to_csv(handle, index=False, header=start == 0)
            progress_callback(min(start + 10000, total), total)
    progress_callback(total, total, True)
