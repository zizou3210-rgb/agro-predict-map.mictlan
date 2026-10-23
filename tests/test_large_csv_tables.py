import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from tabular_io import read_dataframe, read_headers, read_records, write_rows, estimated_manual_grid_rows, large_table_path
from pipeline.nasa_country_region import build_manual_grid_cells
from ce_pipeline.phase01.phase1 import write_xlsx_rows, read_sheet_headers_and_rows
from ce_pipeline.phase04.phase04 import create_phase04_workbook
from pipeline.run_model_pipeline import write_combined_prediction_outputs
from pipeline.common import dataframe_to_geojson
from workbook_preview import build_original_feature_collection_from_xlsx
import server


class LargeCsvTableTests(unittest.TestCase):
    def test_identifiers_literals_dates_empty_values_and_coordinates_roundtrip(self):
        headers = ['Farm', 'Name', 'CE Row ID', 'Date of planting', 'value', '_GPS coordinates_latitude', '_GPS coordinates_longitude']
        rows = [('0001', 'NA', '00002', '2026-04-07', 1.23456789012345, 1.2, 32.5), ('0000', 'á, "maíz"\nsegunda línea', '00003', '', None, 1.3, 32.6)]
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'large.csv'
            write_rows(path, headers, rows, len(rows))
            self.assertEqual(read_headers(path), headers)
            raw_headers, raw_rows = read_sheet_headers_and_rows(path)
            self.assertEqual(raw_headers, headers)
            self.assertEqual(raw_rows[0]['Farm'], '0001')
            self.assertEqual(raw_rows[0]['Name'], 'NA')
            self.assertEqual(raw_rows[1]['Name'], rows[1][1])
            frame = read_dataframe(path)
            self.assertEqual(frame['Farm'].tolist(), ['0001', '0000'])
            self.assertEqual(frame['CE Row ID'].tolist(), ['00002', '00003'])
            self.assertEqual(frame['Name'][0], 'NA')
            self.assertAlmostEqual(frame['value'][0], rows[0][4], places=14)
            self.assertTrue(pd.isna(frame['value'][1]))
            self.assertTrue(pd.isna(frame['Date of planting'][1]))
            mapped = build_original_feature_collection_from_xlsx(path)
            self.assertEqual(len(mapped['features']), 2)
            self.assertEqual(mapped['features'][0]['geometry']['coordinates'], [32.5, 1.2])

    def test_grid_estimate_matches_generated_grid_and_small_tables_keep_excel(self):
        for bounds in [(0, .1, 31, 31.1), (-10.597708, 3.373882, 31.973871, 50.482402)]:
            cells = build_manual_grid_cells(*bounds, cell_size_km=5)
            self.assertEqual(estimated_manual_grid_rows(90, bounds, 5), len(cells) * 90)
        with patch.dict('os.environ', {'APP_LARGE_TABLE_MIN_ROWS': '50000'}):
            self.assertEqual(large_table_path('small.xlsx', 49999), Path('small.xlsx'))
            self.assertEqual(large_table_path('large.xlsx', 50000), Path('large.csv'))

    def test_phase04_csv_generates_no_excel_and_same_normalized_values(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            headers = ['Grain Yield (T/Ha)', 'Farm', 'feature_a', 'Soil type/texture', 'Soil Depth (cm)-How deep do you expect maize roots to grow in this soil?']
            write_xlsx_rows(root / 'input.csv', headers, [('', '0001', 1, 'Loam', '100cm o mas'), ('', '0002', 3, 'Loam', '100cm o mas')], 2)
            definition = {'initial_settings': {'target_column': headers[0]}, 'divisions': {'germplams_identifiers': ['Farm'], 'categorical_data': [], 'cuantitative_data': ['feature_a']}}
            (root / 'definition.json').write_text(json.dumps(definition))
            create_phase04_workbook(root / 'input.csv', root / 'definition.json', root / 'phase04.csv', root / 'log.json', allow_missing_target=True, stream_traceability_workbook=True, normalization_overrides={'feature_a': {'mean': 2, 'std': 1, 'apply_log': False}})
            result = read_dataframe(root / 'phase04_training_input.csv')
            self.assertEqual(result['Farm'].tolist(), ['0001', '0002'])
            self.assertEqual(result['feature_a'].tolist(), [-1., 1.])
            self.assertEqual(list(root.glob('*.xlsx')), [])

    def test_context_export_csv_and_excel_generate_identical_geojson(self):
        df = pd.DataFrame({'Name': ['maíz'], 'Farm': ['0001'], 'Country': ['Uganda'], '_GPS coordinates_latitude': [1.2], '_GPS coordinates_longitude': [32.5], 'Grain Yield predicted': [2.34567891]})
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            legacy_csv, legacy_excel = write_combined_prediction_outputs(df, root)
            expected = dataframe_to_geojson(read_dataframe(legacy_excel), root / 'map.geojson')
            legacy_excel.unlink()
            actual_csv, csv_alias = write_combined_prediction_outputs(df, root, csv_only=True)
            actual = dataframe_to_geojson(read_dataframe(actual_csv), root / 'map.geojson')
            self.assertEqual(actual_csv, csv_alias)
            self.assertEqual(actual, expected)
            self.assertEqual(list(root.glob('*.xlsx')), [])

    def test_csv_download_and_server_overlay_preserve_cell_predictions(self):
        cells = build_manual_grid_cells(0, .1, 31, 31.1, cell_size_km=10)
        features = [{'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [c['center_longitude'], c['center_latitude']]}, 'properties': {'Forecast grid cell id': c['grid_cell_id'], 'Farm': '0001', 'Name': 'maize', 'Grain Yield predicted': float(i + 2)}} for i, c in enumerate(cells)]
        geojson = {'type': 'FeatureCollection', 'metadata': {'total_features': len(features)}, 'features': features}
        summary = {'climate_scope': 'regional_manual', 'tabular_format': 'csv', 'manual_bbox_grid': {'cells': cells}, 'selected_id_header': 'Farm', 'source_name': 'input.xlsx'}
        with patch('server.resolve_prediction_feature_collection', return_value=geojson):
            display = server.build_prediction_display_feature_collection(summary)
            body, name = server._build_manual_grid_prediction_workbook_bytes(summary)
            _, names = server._build_manual_grid_prediction_payload(summary, display)
            overlay = server._build_manual_grid_overlay_base_payload(summary, display, names)
        self.assertTrue(name.endswith('.csv'))
        downloaded = list(csv.DictReader(io.StringIO(body.decode('utf-8'))))
        self.assertEqual(len(downloaded), len(display['features']))
        for record, feature in zip(downloaded, display['features']):
            self.assertEqual(record['Farm'], '0001')
            self.assertEqual(float(record['Grain Yield predicted']), feature['properties']['Grain Yield predicted'])
            self.assertEqual([float(record['Longitude']), float(record['Latitude'])], feature['geometry']['coordinates'])
        self.assertEqual(len(overlay['heat_samples']), len(cells))
