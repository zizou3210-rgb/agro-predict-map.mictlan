import unittest
from unittest.mock import patch
from pipeline.manual_grid_interpolation import build_manual_grid_interpolated_surface


class InterpolationLimitTests(unittest.TestCase):
    def test_large_grid_returns_direct_overlay_without_expensive_interpolation(self):
        cells = [{'grid_cell_id': str(i), 'center_longitude': i, 'center_latitude': 0,
                  'longitude_min': i - .5, 'longitude_max': i + .5,
                  'latitude_min': -.5, 'latitude_max': .5} for i in range(513)]
        with patch('pipeline.manual_grid_interpolation._build_backend_kriging_surface') as kriging, patch('pipeline.manual_grid_interpolation._build_backend_idw_surface') as idw:
            surface = build_manual_grid_interpolated_surface(cells, {str(i): 2.5 for i in range(513)})
        kriging.assert_not_called()
        idw.assert_not_called()
        self.assertEqual(surface['reason'], 'grid_size_limit')
        self.assertEqual(surface['valid_cell_count'], 513)
        self.assertEqual(surface['samples'], [])

    def test_small_grid_keeps_existing_interpolation(self):
        cells = [{'grid_cell_id': str(i), 'center_longitude': i, 'center_latitude': 0,
                  'longitude_min': i - .5, 'longitude_max': i + .5,
                  'latitude_min': -.5, 'latitude_max': .5} for i in range(12)]
        with patch('pipeline.manual_grid_interpolation._build_backend_kriging_surface', return_value=[{'predictedValue': 2.5}]) as kriging:
            surface = build_manual_grid_interpolated_surface(cells, {str(i): 2.5 for i in range(12)})
        kriging.assert_called_once()
        self.assertEqual(surface['method'], 'kriging')
