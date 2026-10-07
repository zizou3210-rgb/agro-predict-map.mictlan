import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from openpyxl import load_workbook

from pipeline.common import dataframe_to_geojson
from pipeline.model.runtime_predict import predict_batches
from pipeline.phase3 import build_final_df
from pipeline.progress import ProgressReporter, write_dataframe_excel


class PredictionStageProgressTests(unittest.TestCase):
    def test_error_marks_incomplete_stage_as_error_and_keeps_counter(self):
        reporter = ProgressReporter(None)
        reporter.update(97, 'Saving workbook', 'working', details={'stage_percent': 98, 'stage_completed': 98, 'stage_total': 100})
        reporter.error('ZIP failure')
        self.assertEqual(reporter._history[-2]['status'], 'error')
        self.assertEqual(reporter._history[-2]['details']['stage_percent'], 98)
        self.assertEqual(reporter._history[-1]['status'], 'error')

    def test_excel_progress_preserves_pandas_cells_and_styles(self):
        df = pd.DataFrame({'text': ['á & soil', None], 'number': [1.25, np.nan], 'flag': [True, False], 'date': pd.to_datetime(['2026-04-07', None])})
        events = []
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            df.to_excel(root / 'old.xlsx', index=False)
            write_dataframe_excel(df, root / 'new.xlsx', lambda *args: events.append(args))
            books = [load_workbook(root / name) for name in ['old.xlsx', 'new.xlsx']]
            try:
                rows = [[[(c.value, c.number_format, c.data_type, c.font.bold) for c in row] for row in book.active] for book in books]
                self.assertEqual(rows[0], rows[1])
            finally:
                for book in books:
                    book.close()
        self.assertEqual(events[0], (0, 12))
        self.assertEqual(events[-1], (12, 12, True))

    def test_normalization_progress_preserves_output(self):
        df = pd.DataFrame({'Gender of the farmer (plot manager)': ['Joint'], 'Soil type/texture': ['Sandy'], 'Grain_moisture_Plot_1': [0]})
        events = []
        pd.testing.assert_frame_equal(build_final_df(df), build_final_df(df, lambda *args: events.append(args)))
        self.assertEqual(events[0], (0, 10))
        self.assertEqual(events[-1], (10, 10, True))

    def test_inference_batches_preserve_values_and_order(self):
        class Model:
            def prediction(self, values):
                return values[:, 0] * 2 + values[:, 1]
        df = pd.DataFrame({'a': np.arange(9000), 'b': np.arange(9000) / 3})
        events = []
        result = predict_batches(Model(), df, lambda *args: events.append(args))
        np.testing.assert_array_equal(result, Model().prediction(df.to_numpy()))
        self.assertEqual(events, [(0, 9000), (4096, 9000), (8192, 9000), (9000, 9000)])

    def test_geojson_counts_invalid_coordinates_without_changing_output(self):
        df = pd.DataFrame({'_GPS coordinates_latitude': [1, None, 2], '_GPS coordinates_longitude': [32, 33, 34], 'Country': ['known'] * 3, 'Grain Yield predicted': [2, 3, 4]})
        events = []
        with tempfile.TemporaryDirectory() as root:
            expected = dataframe_to_geojson(df, Path(root) / 'map.geojson')
            actual = dataframe_to_geojson(df, Path(root) / 'map.geojson', lambda *args: events.append(args))
            self.assertEqual(expected, actual)
            self.assertEqual(json.loads((Path(root) / 'map.geojson').read_text()), actual)
        self.assertEqual(len(actual['features']), 2)
        self.assertEqual(events[-1], (3, 3, True))

    def test_history_keeps_measured_percent_and_finishes_same_stage(self):
        reporter = ProgressReporter(None)
        reporter.update(80, 'Encoding', 'working', details={'stage_percent': 30, 'stage_completed': 3, 'stage_total': 10})
        reporter.update(80, 'Encoding', 'done', details={'stage_percent': 100, 'stage_completed': 10, 'stage_total': 10})
        self.assertEqual(reporter._history[-1]['status'], 'finished')
        self.assertEqual(reporter._history[-1]['details']['stage_percent'], 100)
        reporter.update(90, 'Inference', 'working', details={'stage_percent': 0})
        self.assertEqual(reporter._history[0]['details']['stage_completed'], 10)
        self.assertIn('ended_at', reporter._history[0])
        self.assertEqual(reporter._history[-1]['status'], 'running')
        reporter.close()

class SerializablePredictionModel:
    def prediction(self, values):
        return values[:, 0] * 2


class RuntimePredictionProgressTests(unittest.TestCase):
    def test_real_subprocess_reports_rows_and_keeps_predictions(self):
        import pickle
        import sys
        from types import SimpleNamespace
        from pipeline.model.grain_yield_model import run_prediction_subprocess
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            model_file = root / 'model.pkl'
            with model_file.open('wb') as handle:
                pickle.dump(SerializablePredictionModel(), handle)
            input_csv = root / 'input.csv'
            pd.DataFrame({'value': np.arange(9000)}).to_csv(input_csv, index=False)
            events = []
            with patch('pipeline.model.grain_yield_model.get_featurehero_python', return_value=Path(sys.executable)), patch('pipeline.model.grain_yield_model.get_featurehero_repo', return_value=Path.cwd()):
                run_prediction_subprocess(SimpleNamespace(model_file=model_file), input_csv, root / 'result.json', lambda *args: events.append(args))
            self.assertEqual(json.loads((root / 'result.json').read_text())['predictions'], (np.arange(9000) * 2).tolist())
            self.assertEqual(events[-1], (9000, 9000, True))

class Phase04ProgressIntegrationTests(unittest.TestCase):
    def test_complete_preparation_reports_each_stage_and_preserves_output(self):
        from ce_pipeline.phase04.phase04 import create_phase04_workbook
        from ce_pipeline.phase01.phase1 import write_xlsx
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            headers = ['Grain Yield (T/Ha)', 'Name', 'feature_a', 'Soil type/texture', 'Soil Depth (cm)-How deep do you expect maize roots to grow in this soil?']
            rows = [dict(zip(headers, ['', 'maize', value, 'Loam', '100cm o mas'])) for value in ['1', '3']]
            write_xlsx(root / 'input.xlsx', headers, rows)
            (root / 'definition.json').write_text(json.dumps({'initial_settings': {'target_column': 'Grain Yield (T/Ha)'}, 'divisions': {'categorical_data': [], 'cuantitative_data': ['feature_a'], 'germplams_identifiers': ['Name'], 'DG': []}}))
            events = []
            create_phase04_workbook(root / 'input.xlsx', root / 'definition.json', root / 'output.xlsx', root / 'log.json', allow_missing_target=True, stream_traceability_workbook=True, progress_callback=lambda *args: events.append(args), normalization_overrides={'feature_a': {'mean': 2, 'std': 1, 'apply_log': False}})
            completed = {event[1] for event in events if (event[3] or {}).get('stage_percent') == 100}
            self.assertTrue({'Building phase04prediction', 'Preparing phase04prediction', 'Normalizing fields', 'Standardizing metrics', 'Encoding categories', 'Writing phase04prediction', 'Writing phase04prediction workbook', 'Saving model-ready workbook'} <= completed)
            result = pd.read_csv(root / 'output_training_input.csv')
            self.assertEqual(result['feature_a'].tolist(), [-1, 1])
            self.assertEqual(len(result), 2)
