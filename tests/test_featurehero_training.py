"""Exercise the actual background training contract used by CE Pipeline."""
import csv
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from pipeline import phase_analysis as analysis

ROOT = Path(__file__).resolve().parents[1]
PARAMS = {'number_generation':10,'number_population':10,
    'machines':['extreme_gradient_boost_regression'],'metric':'mean_absolute_error'}


class FeatureHeroTrainingTest(unittest.TestCase):
    def launch(self, root, valid=True):
        data = root / 'input.csv'
        with data.open('w', newline='', encoding='utf-8') as handle:
            writer=csv.writer(handle)
            writer.writerow(['x1','x2','x3','x4','yield'])
            for i in range(80):
                writer.writerow([i,i%7,(i%11)*.2,(i%5)*.7,2+i*.03 if valid else 'invalid'])
        sleep = time.sleep
        with (
            patch.dict(os.environ, {'HOME':str(root),'USERPROFILE':str(root),'OMP_NUM_THREADS':'1'}),
            patch.object(analysis,'JOBS_FILE',root/'.featurehero/jobs.pids'),
            patch.object(analysis,'load_app_env'),
            patch.object(analysis,'get_featurehero_python',return_value=Path(sys.executable)),
            patch.object(analysis,'get_featurehero_repo',return_value=ROOT/'resources/featurehero'),
            patch.object(analysis,'get_featurehero_params_json',return_value=json.dumps(PARAMS)),
            patch.object(analysis,'get_featurehero_job_timeout_seconds',return_value=45),
            patch.object(analysis.time,'sleep',side_effect=lambda seconds:sleep(min(seconds,.05))),
        ):
            return analysis.launch_featurehero(data,root,'yield')

    def test_background_training_creates_model_features_and_training_table(self):
        with tempfile.TemporaryDirectory(prefix='featurehero training ') as directory:
            root = Path(directory)
            _, info, workspace = self.launch(root)
            for name in ('best_model_sort_original.pkl','best_features_sort_original.pkl','sort_original.csv'):
                self.assertGreater((workspace/name).stat().st_size,0)
            log = Path(info['log_file']).read_text(encoding='utf-8')
            self.assertIn('Process completed.',log)

    def test_background_failure_exposes_original_error_instead_of_missing_pickle(self):
        with tempfile.TemporaryDirectory(prefix='featurehero failed ') as directory:
            with self.assertRaises(RuntimeError) as raised:
                self.launch(Path(directory),valid=False)
            self.assertIn('ValueError',str(raised.exception))
            self.assertIn('Error validating file',str(raised.exception))
            self.assertIn('Training log:',str(raised.exception))
            from server import format_called_process_error
            import subprocess
            visible = format_called_process_error(subprocess.CalledProcessError(1, [], stderr=str(raised.exception)))
            self.assertIn('ValueError',visible)
            self.assertIn('Error validating file',visible)

    def test_invalid_artifacts_do_not_register_an_empty_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            log=root/'training.log'
            log.write_text('Traceback\nValueError: invalid training data',encoding='utf-8')
            with patch.object(analysis,'get_model_dir') as registry:
                with self.assertRaisesRegex(RuntimeError,'invalid training data'):
                    analysis.persist_model_artifacts('model',root,'yield','yield',root,
                        {'log_file':str(log)},root/'input.csv')
                registry.assert_not_called()

    def test_plot_failure_does_not_prevent_saving_trained_model(self):
        sys.path.insert(0,str(ROOT/'resources/featurehero'))
        try:
            from featurehero.services.optimizations.optimization_genetic_algorithm import GeneticAlgorithm
            from featurehero.services.optimizations import optimization_genetic_algorithm as module
            from unittest.mock import Mock
            import joblib
            import io
            from contextlib import redirect_stdout
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                population = Mock()
                population.machine='trained model'
                population.features_chromosome=[True,False]
                population.to_dictionary.return_value={'index_metric':.1,'machine_name':'test'}
                algorithm=object.__new__(GeneticAlgorithm)
                algorithm._global_population=[population]
                algorithm._file_machine=Mock()
                algorithm._file_machine.file_data.folder_path=str(root)
                storage=algorithm._file_machine.storage_file
                storage.adding_prefix_file_name_only_file.return_value='optimization_sort_original.csv'
                storage.adding_prefix_name_extension.side_effect=lambda prefix,extension:str(root/f'{prefix}_sort_original.{extension}')
                with patch.object(module,'create_graph_model_index',side_effect=OSError('graphics unavailable')), redirect_stdout(io.StringIO()):
                    algorithm.export()
                self.assertEqual(joblib.load(root/'best_model_sort_original.pkl'),'trained model')
                self.assertEqual(joblib.load(root/'best_features_sort_original.pkl'),[True,False])
        finally:
            sys.path.pop(0)


if __name__=='__main__':
    unittest.main()
