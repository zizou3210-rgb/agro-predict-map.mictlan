import errno
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline import progress
from ce_pipeline.phase03 import script03
from ce_pipeline.phase05 import phase05
from ce_pipeline.phase06 import phase06
from server import write_json_file_atomic


def windows_lock(code=5):
    error = PermissionError(errno.EACCES, "Windows file temporarily locked")
    error.winerror = code
    return error


class AtomicProgressTest(unittest.TestCase):
    def test_transient_windows_locks_preserve_old_snapshot_until_replace(self):
        real_replace = progress.os.replace
        for code in (5, 32, 33):
            with self.subTest(winerror=code), tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / "progress.json"
                target.write_text('{"old": true}', encoding="utf-8")
                attempts = []

                def replace(source, destination):
                    # Both files can be read: the temporary writer is closed.
                    self.assertEqual(json.loads(Path(source).read_text(encoding="utf-8")), {"new": "maíz"})
                    self.assertEqual(json.loads(target.read_text()), {"old": True})
                    attempts.append(source)
                    if len(attempts) < 3:
                        raise windows_lock(code)
                    real_replace(source, destination)

                with patch.object(progress.os, "replace", side_effect=replace), patch.object(progress.time, "sleep") as sleep:
                    progress.write_json_atomic(target, {"new": "maíz"})
                self.assertEqual(len(attempts), 3)
                self.assertEqual(sleep.call_count, 2)
                self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"new": "maíz"})
                self.assertEqual(list(target.parent.iterdir()), [target])

    def test_persistent_lock_is_bounded_and_does_not_destroy_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "progress.json"
            target.write_text('{"old": true}', encoding="utf-8")
            error = windows_lock()
            with patch.object(progress.os, "replace", side_effect=error) as replace, patch.object(progress.time, "sleep") as sleep:
                with self.assertRaises(PermissionError) as raised:
                    progress.write_json_atomic(target, {"new": True})
            self.assertIs(raised.exception, error)
            self.assertEqual(replace.call_count, 12)
            self.assertEqual(sleep.call_count, 11)
            self.assertLess(sum(call.args[0] for call in sleep.call_args_list), 3)
            self.assertEqual(json.loads(target.read_text()), {"old": True})
            self.assertEqual(list(target.parent.iterdir()), [target])

    def test_other_io_errors_are_not_retried(self):
        for error in (OSError(errno.ENOSPC, "Disk full"), PermissionError(errno.EACCES, "Not writable")):
            with self.subTest(error=error), tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / "progress.json"
                with patch.object(progress.os, "replace", side_effect=error) as replace, patch.object(progress.time, "sleep") as sleep:
                    with self.assertRaises(OSError):
                        progress.write_json_atomic(target, {"new": True})
                replace.assert_called_once()
                sleep.assert_not_called()
                self.assertEqual(list(target.parent.iterdir()), [])

    def test_serialization_failure_cleans_up_and_preserves_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "progress.json"
            target.write_text('{"old": true}', encoding="utf-8")
            with self.assertRaises(TypeError):
                progress.write_json_atomic(target, {"invalid": object()})
            self.assertEqual(json.loads(target.read_text()), {"old": True})
            self.assertEqual(list(target.parent.iterdir()), [target])

    def test_progress_writers_recover_from_windows_lock(self):
        writers = {
            "server": lambda path: write_json_file_atomic(path, {"percent": 16}),
            "reporter": lambda path: progress.ProgressReporter(path)._write({"percent": 16}),
            "phase03": lambda path: script03.write_progress(path, percent=16, stage="Climate", message="Working"),
            "phase05": lambda path: phase05.write_progress(path, percent=16, stage="Predicting", message="Working"),
            "phase06": lambda path: phase06.write_progress(path, percent=16, stage="Predicting", message="Working"),
        }
        real_replace = progress.os.replace
        for name, write in writers.items():
            with self.subTest(writer=name), tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / "ce_summary_progress.json"
                attempts = []

                def replace(source, destination):
                    attempts.append(source)
                    if len(attempts) == 1:
                        raise windows_lock()
                    real_replace(source, destination)

                with patch.object(progress.os, "replace", side_effect=replace), patch.object(progress.time, "sleep"):
                    write(target)
                self.assertEqual(len(attempts), 2)
                self.assertEqual(json.loads(target.read_text())["percent"], 16)
                self.assertEqual(list(target.parent.iterdir()), [target])
