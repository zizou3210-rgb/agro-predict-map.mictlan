import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from ce_pipeline.prediction.prediction import _restore_selected_id_column_in_phase04_workbook


class IdentifierRestorationProgressTests(unittest.TestCase):
    def run_restore(self, root, header, events):
        _restore_selected_id_column_in_phase04_workbook(phase03_workbook=root / 'source.xlsx', phase04_workbook=root / 'output.xlsx', selected_id_header=header, progress_callback=lambda *args: events.append(args))

    def test_missing_identifier_skips_full_reads_and_finishes_counter(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            pd.DataFrame({'value': [1]}).to_excel(root / 'source.xlsx', index=False)
            pd.DataFrame({'value': [2]}).to_excel(root / 'output.xlsx', index=False)
            events = []
            with patch('ce_pipeline.prediction.prediction.pd.read_excel') as reading:
                self.run_restore(root, '__clear_selection__', events)
                reading.assert_not_called()
            self.assertEqual(events[0][3]['stage_percent'], 0)
            self.assertEqual(events[-1][3]['stage_percent'], 100)
            self.assertEqual(events[-1][1], 'Checking selected identifier')

    def test_existing_identifier_skips_full_reads_and_does_not_rewrite(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            pd.DataFrame({'ID': ['source']}).to_excel(root / 'source.xlsx', index=False)
            pd.DataFrame({'ID': ['existing']}).to_excel(root / 'output.xlsx', index=False)
            previous = (root / 'output.xlsx').read_bytes()
            with patch('ce_pipeline.prediction.prediction.pd.read_excel') as reading:
                self.run_restore(root, 'ID', [])
                reading.assert_not_called()
            self.assertEqual((root / 'output.xlsx').read_bytes(), previous)

    def test_restore_by_row_id_preserves_alignment_and_reports_all_stages(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            pd.DataFrame({'CE Row ID': ['a', 'b'], 'ID': ['A', 'B']}).to_excel(root / 'source.xlsx', index=False)
            pd.DataFrame({'CE Row ID': ['b', 'a'], 'value': [2, 1]}).to_excel(root / 'output.xlsx', index=False)
            events = []
            self.run_restore(root, 'ID', events)
            result = pd.read_excel(root / 'output.xlsx')
            self.assertEqual(result['ID'].tolist(), ['B', 'A'])
            self.assertEqual(result['value'].tolist(), [2, 1])
            completed = {e[1] for e in events if e[3]['stage_percent'] == 100}
            self.assertEqual(completed, {'Checking selected identifier', 'Loading identifier restoration workbooks', 'Restoring selected identifier', 'Saving restored identifier workbook'})

    def test_restore_by_position_preserves_values(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            pd.DataFrame({'ID': ['A', 'B']}).to_excel(root / 'source.xlsx', index=False)
            pd.DataFrame({'value': [1, 2]}).to_excel(root / 'output.xlsx', index=False)
            self.run_restore(root, 'ID', [])
            self.assertEqual(pd.read_excel(root / 'output.xlsx')['ID'].tolist(), ['A', 'B'])

    def test_mismatched_rows_leave_output_unchanged(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            pd.DataFrame({'ID': ['A', 'B']}).to_excel(root / 'source.xlsx', index=False)
            pd.DataFrame({'value': [1]}).to_excel(root / 'output.xlsx', index=False)
            previous = (root / 'output.xlsx').read_bytes()
            self.run_restore(root, 'ID', [])
            self.assertEqual((root / 'output.xlsx').read_bytes(), previous)
