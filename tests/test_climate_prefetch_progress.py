"""Progress must remain truthful while cache checks give way to slow downloads."""
import json
from datetime import date
from pathlib import Path
from threading import Event
import tempfile
import unittest
from unittest.mock import patch

from ce_pipeline.phase03 import script03


class ClimatePrefetchProgressTest(unittest.TestCase):
    def test_slow_download_reports_current_work_without_advancing_completed_files(self):
        release=Event()
        reports=[]
        messages=[]
        def resolve(dataset, current_date, cache):
            if dataset == 'chirts_tmax':
                script03.append_thread_climate_debug_log('raster_download_attempt_started',{'attempt':1})
                if not release.wait(8):
                    raise RuntimeError('test download was not released')
            return cache/f'{dataset}.tif', dataset != 'chirps'
        def progress(percent, stage, message, details):
            reports.append(dict(details))
            messages.append(message)
            # Allow two real progress ticks during a blocked request.
            if details['stage_elapsed_seconds'] >= 1.8:
                release.set()
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(script03,'resolve_shared_chc_cache_dir',return_value=Path(directory)),
            patch.object(script03,'resolve_phase03_worker_limit',return_value=1),
            patch.object(script03,'_resolve_raster_path',side_effect=resolve),
            patch.object(script03,'_validate_chc_raster_file'),
        ):
            try:
                result=script03.prefetch_chc_rasters([date(2026,1,1)],progress_callback=progress)
            finally:
                release.set()
        waiting=[report for report in reports if report['stage_completed']==1 and report['climate_prefetch_active_tasks']]
        self.assertGreaterEqual(len(waiting),2)
        self.assertTrue(all(report['stage_total']==3 for report in waiting))
        self.assertTrue(all(report['stage_eta_seconds'] is None for report in waiting))
        self.assertTrue(all(report['climate_prefetch_downloaded']==0 for report in waiting))
        self.assertTrue(all(report['climate_prefetch_cached']==1 for report in waiting))
        self.assertTrue(any(task['operation']=='downloading raster' and task['attempt']==1
            for report in waiting for task in report['climate_prefetch_active_tasks']))
        self.assertGreater(waiting[-1]['stage_elapsed_seconds'],waiting[0]['stage_elapsed_seconds'])
        self.assertGreater(waiting[-1]['climate_prefetch_seconds_since_completion'],.8)
        self.assertTrue(any('ETA: unavailable' in message for message in messages))
        self.assertEqual(reports[-1]['stage_completed'],3)
        self.assertEqual(reports[-1]['stage_percent'],100)
        self.assertEqual(reports[-1]['climate_prefetch_active_tasks'],[])
        self.assertEqual(result['cached'],1)
        self.assertEqual(result['downloaded'],2)

    def test_download_eta_does_not_use_the_faster_cache_hit_rate(self):
        allow_download=Event()
        finish=Event()
        reports=[]
        def resolve(dataset,current_date,cache):
            if dataset=='chirts_tmax':
                allow_download.wait(4)
            if dataset=='chirts_tmin':
                finish.wait(4)
            return cache/f'{dataset}.tif',dataset!='chirps'
        def report(percent,stage,message,details):
            reports.append(details)
            if details['stage_completed']==1:
                allow_download.set()
            if details['stage_completed']==2:
                finish.set()
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(script03,'resolve_shared_chc_cache_dir',return_value=Path(directory)),
            patch.object(script03,'resolve_phase03_worker_limit',return_value=1),
            patch.object(script03,'_resolve_raster_path',side_effect=resolve),
            patch.object(script03,'_validate_chc_raster_file'),
        ):
            try:
                script03.prefetch_chc_rasters([date(2026,1,1)],progress_callback=report)
            finally:
                allow_download.set()
                finish.set()
        middle=next(details for details in reports if details['stage_completed']==2)
        rate=middle['climate_prefetch_download_files_per_second']
        self.assertGreater(rate,0)
        self.assertAlmostEqual(middle['stage_eta_seconds'],1/rate,delta=.01)
        self.assertGreater(middle['stage_eta_seconds'],1/middle['stage_rate_per_second']*1.5)

    def test_retry_wait_is_visible_in_written_progress(self):
        release=Event()
        with tempfile.TemporaryDirectory() as directory:
            progress_file=Path(directory)/'progress.json'
            reports=[]
            def resolve(dataset, current_date, cache):
                if dataset=='chirps':
                    script03.append_thread_climate_debug_log('raster_download_retry_scheduled',{'attempt':2,'sleep_seconds':8})
                    release.wait(6)
                return cache/f'{dataset}.tif',True
            def callback(percent,stage,message,details):
                script03.write_progress(progress_file,percent=percent,stage=stage,message=message,details=details)
                snapshot=json.loads(progress_file.read_text())
                reports.append(snapshot)
                if any(task['operation']=='waiting to retry download' for task in details['climate_prefetch_active_tasks']):
                    release.set()
            with (
                patch.object(script03,'resolve_shared_chc_cache_dir',return_value=Path(directory)),
                patch.object(script03,'resolve_phase03_worker_limit',return_value=1),
                patch.object(script03,'_resolve_raster_path',side_effect=resolve),
                patch.object(script03,'_validate_chc_raster_file'),
            ):
                try:
                    script03.prefetch_chc_rasters([date(2026,1,1)],progress_callback=callback)
                finally:
                    release.set()
            retries=[report for report in reports if 'waiting to retry download' in report['message']]
            self.assertTrue(retries)
            self.assertIn('Attempt: 2/',retries[0]['message'])
            self.assertIn('Retry delay: 8s',retries[0]['message'])
            self.assertEqual(retries[0]['details']['stage_completed'],0)
            self.assertIsNone(retries[0]['details']['stage_eta_seconds'])

    def test_failed_prefetch_cancels_queued_work_and_reports_the_error(self):
        messages=[]
        release=Event()
        calls=[]
        def fail(dataset, current_date, cache):
            calls.append(dataset)
            if len(calls)>1 and not release.wait(2):
                release.set()
            raise RuntimeError('network unavailable')
        def report(percent,stage,message,details):
            messages.append(message)
            if 'Climate raster preparation failed' in message:
                release.set()
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(script03,'resolve_shared_chc_cache_dir',return_value=Path(directory)),
            patch.object(script03,'resolve_phase03_worker_limit',return_value=1),
            patch.object(script03,'_resolve_raster_path',side_effect=fail),
        ):
            try:
                with self.assertRaisesRegex(RuntimeError,'network unavailable'):
                    script03.prefetch_chc_rasters([date(2026,1,day) for day in range(1,20)],progress_callback=report)
            finally:
                release.set()
            self.assertLess(len(calls),57)
            self.assertTrue(any('Climate raster preparation failed: network unavailable' in message for message in messages))


if __name__=='__main__':
    unittest.main()
