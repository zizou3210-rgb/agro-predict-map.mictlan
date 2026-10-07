import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
from ce_pipeline.phase01.phase1 import read_sheet_headers_and_rows, write_xlsx
from ce_pipeline.prediction import prediction as flow
from pipeline.model.grain_yield_model import GrainYieldPredictionOutputs
from pipeline.progress import ProgressReporter, work_progress, write_dataframe_csv, reported_operation


class FarmUiProgressTests(unittest.TestCase):
    def test_csv_counter_preserves_pandas_bytes_across_chunks(self):
        df = pd.DataFrame({'Farm': ['á, farm'] * 10003, 'value': [1.25] * 10002 + [None]})
        events = []
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            df.to_csv(root / 'expected.csv', index=False)
            write_dataframe_csv(df, root / 'actual.csv', lambda *args: events.append(args))
            self.assertEqual((root / 'actual.csv').read_bytes(), (root / 'expected.csv').read_bytes())
        self.assertEqual(events[-1], (10003, 10003, True))
        self.assertIn((10000, 10003), events)

    def test_operation_error_is_not_reported_as_complete(self):
        events = []
        def fail():
            raise ValueError('failed')
        with self.assertRaises(ValueError):
            reported_operation(lambda *args: events.append(args), 99, 'Saving', 'phase05', fail)
        self.assertEqual([e[3]['stage_percent'] for e in events], [0])

    def test_farm_aggregation_and_display_preserve_values(self):
        df = pd.DataFrame({'Name': ['maize'] * 3, 'Farm': ['A', 'A', 'B'], 'Forecast grid cell id': ['cell'] * 3, '_GPS coordinates_latitude': [1] * 3, '_GPS coordinates_longitude': [32] * 3, 'Grain Yield predicted': [2, 4, 8]})
        events = []
        expected = flow._aggregate_prediction_dataframe_by_selected_id(df, selected_id_header='Farm')
        actual = flow._aggregate_prediction_dataframe_by_selected_id(df, selected_id_header='Farm', progress_callback=lambda *args: events.append(args))
        pd.testing.assert_frame_equal(expected, actual)
        self.assertEqual(actual['Grain Yield predicted'].tolist(), [3, 8])
        self.assertEqual(events[-1][3]['stage_percent'], 100)
        expected_display = flow._aggregate_manual_grid_prediction_dataframe_for_display(actual)
        actual_display = flow._aggregate_manual_grid_prediction_dataframe_for_display(actual, progress_callback=lambda *args: events.append(args))
        pd.testing.assert_frame_equal(expected_display, actual_display)
        self.assertEqual(actual_display['Farm'].tolist(), ['B'])
        self.assertEqual(events[-1][3]['stage_percent'], 100)

    def test_farm_flow_reports_executed_processes_to_persisted_ui_history(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            definition = {'initial_settings': {'target_column': 'Yield', 'longitude_column': 'Longitude', 'latitude_column': 'Latitude', 'planting_date_column': 'Planting', 'harvesting_date_column': 'Harvesting', 'soil_texture_column': 'SoilTexture', 'soil_depth_column': 'SoilDepth'}, 'divisions': {'germplams_identifiers': ['Name'], 'categorical_data': [], 'cuantitative_data': ['feature_a'], 'DG': []}}
            definition_path = root / 'definition.json'
            definition_path.write_text(json.dumps(definition))
            df = pd.DataFrame({'Name': ['maize', 'maize'], 'Farm': ['A', 'B'], 'feature_a': [1., 3.], 'Yield': [2., 3.], 'Latitude': [1., 1.], 'Longitude': [32., 32.], 'Planting': ['2026-04-07'] * 2, 'Harvesting': ['2026-09-05'] * 2, 'SoilTexture': ['Loam'] * 2, 'SoilDepth': ['100cm o mas'] * 2})
            df.to_excel(root / 'input.xlsx', index=False)
            reporter = ProgressReporter(root / 'progress.json', heartbeat_seconds=60)
            def callback(percent, stage, message, details=None):
                reporter.update(percent, stage, message, details=details)
            # Climate acquisition and model inference have separate regression tests;
            # this small integration checks the real Farm orchestration and exports.
            def climate(source, definition_file, output, log_file, **kwargs):
                headers, records = read_sheet_headers_and_rows(source)
                for row in records:
                    row.update({'_GPS coordinates_latitude': '1', '_GPS coordinates_longitude': '32', 'Country': 'Uganda', 'Forecast grid cell id': 'cell', 'Forecast grid cell index': 1, 'Soil type/texture': 'Loam', 'Soil Depth (cm)-How deep do you expect maize roots to grow in this soil?': '100cm o mas'})
                headers = list(records[0])
                write_xlsx(output, headers, records)
                return {'nasa': {'climate_input_row_count': 2}, 'soil': {}}
            def inference(csv_file, model_dir, selected_model_id=None, progress_callback=None):
                model_dir.mkdir(parents=True, exist_ok=True)
                source = pd.read_csv(csv_file)
                result = source.copy()
                result['Grain Yield predicted'] = [4., 8.]
                report = work_progress(progress_callback, 96, 'Running saved model prediction', phase='phase05')
                report(0, 2); report(2, 2, True)
                output_csv, output_xlsx = model_dir / 'prediction.csv', model_dir / 'prediction.xlsx'
                result.to_csv(output_csv, index=False); result.to_excel(output_xlsx, index=False)
                return GrainYieldPredictionOutputs(result, source, csv_file, output_csv, output_xlsx, 'test model', ['feature_a'], {'model_id': 'test'})
            try:
                with patch.object(flow, '_resolve_saved_model', return_value=(SimpleNamespace(metadata={}, model_dir=root), definition, definition_path)), patch.object(flow, 'validate_saved_model_prediction_workbook'), patch.object(flow, 'create_phase03_workbook', side_effect=climate), patch('ce_pipeline.phase05.phase05.run_grain_yield_prediction', side_effect=inference):
                    outputs = flow.run_ce_saved_model_prediction(root / 'input.xlsx', root / 'run', selected_model_id='test', forecast_planting_date='2026-04-07', forecast_harvesting_date='2026-09-05', selected_germplasm_names=['maize'], selected_germplasm_row_ids=[], regional_bounds_label='test', regional_bounds_latitude_min=0, regional_bounds_latitude_max=1, regional_bounds_longitude_min=31, regional_bounds_longitude_max=32, selected_id_header='Farm', use_source_row_dates=False, progress_callback=callback)
                history = json.loads((root / 'progress.json').read_text())['activity']
                completed = {e['stage'] for e in history if e.get('details', {}).get('stage_percent') == 100}
                expected = {'Reading Farm prediction input', 'Saving Farm prediction input', 'Normalizing fields', 'Standardizing metrics', 'Encoding categories', 'Saving model-ready workbook', 'Checking selected identifier', 'Preparing saved model prediction', 'Resolving prediction countries', 'Running saved model prediction', 'Merging prediction results', 'Normalizing merged prediction fields', 'Saving prediction context CSV', 'Saving prediction context workbook', 'Reading prediction results', 'Aggregating predictions by selected identifier', 'Saving final prediction workbook', 'Saving final prediction CSV', 'Selecting display predictions by grid cell', 'Preparing final map output', 'Preparing display grid', 'Saving prediction summary'}
                self.assertEqual(expected - completed, set())
                self.assertGreater(len(history), 30)
                self.assertTrue(all(e.get('status') == 'finished' for e in history))
                self.assertEqual([(e['stage'], e.get('details', {}).get('stage_percent')) for e in history if e.get('details', {}).get('stage_percent') != 100], [])
                self.assertTrue(outputs.summary_file.exists())
                self.assertEqual(outputs.geojson['features'][0]['properties']['Farm'], 'B')
                self.assertEqual(outputs.geojson['features'][0]['properties']['Grain Yield predicted'], 8.)
                self.assertEqual(len(pd.read_csv(outputs.summary['prediction_csv'])), 2)
            finally:
                reporter.close()
