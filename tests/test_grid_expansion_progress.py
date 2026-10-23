import unittest
from preprocess import ea_pipeline
from tests.test_locality_workflows import build_base_record


class GridExpansionProgressTests(unittest.TestCase):
    def test_progress_preserves_expanded_rows_and_reports_actual_total(self):
        records = [build_base_record(), {**build_base_record(), 'Name': 'second'}]
        override = {'regional_bounds_latitude_min': -.05, 'regional_bounds_latitude_max': .05, 'regional_bounds_longitude_min': 32, 'regional_bounds_longitude_max': 32.05, 'nasa_grid_resolution_km': 10, 'forecast_planting_date': '2026-04-07', 'forecast_harvesting_date': '2026-09-05'}
        expected = ea_pipeline.expand_records_for_manual_bbox_localities(records, override)
        events = []
        actual = ea_pipeline.expand_records_for_manual_bbox_localities(records, override, lambda *args: events.append(args))
        self.assertEqual(expected, actual)
        total = len(actual[0])
        self.assertEqual(events[0], (0, total))
        self.assertEqual(events[-1], (total, total, True))
        self.assertEqual([event[0] for event in events[1:-1]], list(range(1, total + 1)))

    def test_source_dates_preserve_full_record_projection(self):
        record = build_base_record()
        override = {'regional_bounds_latitude_min': -.05, 'regional_bounds_latitude_max': .05, 'regional_bounds_longitude_min': 32, 'regional_bounds_longitude_max': 32.05, 'nasa_grid_resolution_km': 10, 'use_source_row_dates': True}
        events = []
        result = ea_pipeline.expand_records_for_manual_bbox_localities([record, record], override, lambda *args: events.append(args))
        self.assertEqual(result[2]['projected_germplasm_count'], 2)
        self.assertEqual(events[-1], (len(result[0]), len(result[0]), True))
