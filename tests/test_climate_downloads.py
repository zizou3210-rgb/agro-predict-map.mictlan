import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ce_pipeline.phase03 import script03


class RasterResponse(io.BytesIO):
    def __init__(self, payload, content_length=None):
        super().__init__(payload)
        self.headers = {"Content-Length": str(len(payload) if content_length is None else content_length)}


class ClimateDownloadsTest(unittest.TestCase):
    def test_download_uses_blocks_and_saves_complete_payload(self):
        payload = b"raster" * 100000
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "raster.tif"
            response = RasterResponse(payload)
            with patch.object(script03, "urlopen", return_value=response):
                script03._download_with_retries("https://example.test/raster", target)
            self.assertEqual(target.read_bytes(), payload)
            self.assertEqual(list(target.parent.glob("*.tmp")), [])

    def test_trickling_download_reaches_deadline_then_retries(self):
        clock = [1000.0]
        controlled_time = Mock(wraps=script03.time)
        controlled_time.monotonic.side_effect = lambda: clock[0]
        controlled_time.sleep = Mock()
        slow = RasterResponse(b"partial")
        reads = []

        def trickle(size):
            reads.append(size)
            clock[0] += 61
            return b"x"

        slow.read1 = trickle
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "raster.tif"
            with patch.object(script03, "time", controlled_time), patch.object(
                script03, "urlopen", side_effect=[slow, RasterResponse(b"complete")],
            ) as download, patch.object(script03, "append_thread_climate_debug_log") as log:
                script03._download_with_retries("https://example.test/raster", target)
            self.assertEqual(len(reads), 2)
            self.assertEqual(download.call_count, 2)
            controlled_time.sleep.assert_called_once()
            events = [call.args[0] for call in log.call_args_list]
            self.assertIn("raster_download_progress", events)
            self.assertIn("raster_download_retry_scheduled", events)
            self.assertEqual(target.read_bytes(), b"complete")

    def test_incomplete_download_never_replaces_existing_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "raster.tif"
            target.write_bytes(b"existing cache")
            with patch.object(script03, "urlopen", return_value=RasterResponse(b"partial", 100)), patch.object(
                script03.ea_pipeline, "MAX_RETRIES", 1,
            ):
                with self.assertRaisesRegex(RuntimeError, "Could not download"):
                    script03._download_with_retries("https://example.test/raster", target)
            self.assertEqual(target.read_bytes(), b"existing cache")
            self.assertEqual(list(target.parent.glob("*.tmp")), [])
