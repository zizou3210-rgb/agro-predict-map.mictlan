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
# A smoke test of the real worker/export lifecycle, not a model-quality search.
ROWS = 32
PARAMS = {'number_generation':10,'number_population':10,
    'machines':['extreme_gradient_boost_regression'],'metric':'mean_absolute_error'}


class FeatureHeroTrainingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.enterClassContext(patch.object(sys, 'path', [str(ROOT/'resources/featurehero'), *sys.path]))

    def launch(self, root, valid=True):
        data = root / 'input.csv'
        with data.open('w', newline='', encoding='utf-8') as handle:
            writer=csv.writer(handle)
            writer.writerow(['x1','x2','x3','x4','yield'])
            for i in range(ROWS):
                writer.writerow([i,i%7,(i%11)*.2,(i%5)*.7,2+i*.03 if valid else 'invalid'])
        sleep = time.sleep
        with (
            patch.dict(os.environ, {'HOME':str(root),'USERPROFILE':str(root),'OMP_NUM_THREADS':'1','FEATUREHERO_N_JOBS':'1'}),
            patch.object(analysis,'JOBS_FILE',root/'.featurehero/jobs.pids'),
            patch.object(analysis,'load_app_env'),
            patch.object(analysis,'get_featurehero_python',return_value=Path(sys.executable)),
            patch.object(analysis,'get_featurehero_repo',return_value=ROOT/'resources/featurehero'),
            patch.object(analysis,'get_featurehero_params_json',return_value=json.dumps(PARAMS)),
            patch.object(analysis,'get_featurehero_job_timeout_seconds',return_value=120),
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
            import joblib
            import numpy as np
            import pandas as pd
            model = joblib.load(workspace/'best_model_sort_original.pkl')
            mask = joblib.load(workspace/'best_features_sort_original.pkl')
            frame = pd.read_csv(workspace/'sort_original.csv').drop(columns=['yield'])
            prediction = model.prediction(frame.loc[:, mask].to_numpy())
            self.assertEqual(len(prediction), ROWS)
            self.assertTrue(np.isfinite(prediction).all())

    def test_timeout_stops_worker_before_propagating_error(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            info={'file_path':str(root/'input.csv'),'target_column':'yield'}
            with (
                patch.object(analysis,'load_app_env'),
                patch.object(analysis,'get_featurehero_python',return_value=Path(sys.executable)),
                patch.object(analysis,'get_featurehero_repo',return_value=root),
                patch.object(analysis,'get_featurehero_params_json',return_value='{}'),
                patch.object(analysis,'read_jobs',side_effect=[{}, {'123456789':info}]),
                patch.object(analysis.subprocess,'run',return_value=Mock(returncode=0)),
                patch.object(analysis,'get_featurehero_job_timeout_seconds',return_value=0),
                patch.object(analysis.time,'monotonic',side_effect=[0,1]),
                patch.object(analysis,'is_pid_running',return_value=True),
                patch.object(analysis,'terminate_featurehero_job') as stop,
            ):
                with self.assertRaises(TimeoutError):
                    analysis.launch_featurehero(root/'input.csv',root,'yield')
                stop.assert_called_once_with(123456789)

    def test_cancelled_worker_releases_open_log_before_directory_cleanup(self):
        import subprocess
        with tempfile.TemporaryDirectory(prefix='worker locked log ') as directory:
            log=Path(directory)/'worker.log'
            process=subprocess.Popen([sys.executable,'-c',
                "import sys,time; f=open(sys.argv[1],'w'); f.write('ready'); f.flush(); time.sleep(120)",str(log)])
            try:
                deadline=time.monotonic()+10
                while not log.exists() and time.monotonic()<deadline:
                    time.sleep(.02)
                self.assertTrue(log.exists())
                analysis.terminate_featurehero_job(process.pid)
                process.wait(timeout=5)
                log.unlink()  # Windows rejects this if the worker still holds the file.
                self.assertFalse(log.exists())
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)

    def test_crossover_does_not_share_or_modify_parent_estimators(self):
        from unittest.mock import Mock
        from featurehero.services.machines.machine import ExtremeGradientBoostRegression
        from featurehero.services.optimizations.optimization_genetic_algorithm import GeneticAlgorithm, GeneticIndividual
        from featurehero.core.metrics.metric_enums import MetricEnum
        metric=MetricEnum.MEAN_ABSOLUTE_ERROR
        parents=[GeneticIndividual(machine=ExtremeGradientBoostRegression(metric_selection=metric),metric_selection=metric) for _ in range(2)]
        for parent in parents:
            parent.set_features_chromosome([True,False,True])
        before=[{key:value.value for key,value in parent.machine.hyper_parameters.items()} for parent in parents]
        algorithm=object.__new__(GeneticAlgorithm)
        algorithm._file_machine=Mock(columns_name_with_out_target=['x1','x2','x3'])
        algorithm._genetic_parameters=Mock(metric_selection=metric)
        children=algorithm._crossover(*parents)
        self.assertIsNot(children[0].machine,children[1].machine)
        for child in children:
            for parent in parents:
                self.assertIsNot(child.machine,parent.machine)
        sibling_value=children[1].machine.hyper_parameters['n_estimators'].value
        children[0].machine.hyper_parameters['n_estimators'].set_value(17)
        self.assertEqual(children[1].machine.hyper_parameters['n_estimators'].value,sibling_value)
        for parent, expected in zip(parents,before):
            self.assertEqual({key:value.value for key,value in parent.machine.hyper_parameters.items()},expected)

    def test_smoke_test_cpu_limit_is_applied_to_xgboost(self):
        from featurehero.services.machines.machine import ExtremeGradientBoostRegression
        with patch.dict(os.environ, {'FEATUREHERO_N_JOBS':'1'}):
            machine=ExtremeGradientBoostRegression()
            machine.build_machine()
            self.assertEqual(machine._machine.get_params()['n_jobs'],1)

    def test_progress_and_console_output_share_a_single_log_handle(self):
        sys.path.insert(0,str(ROOT/'resources/featurehero'))
        try:
            from featurehero.main import log_progress_from_queue
            from contextlib import redirect_stdout
            from queue import Queue
            with tempfile.TemporaryDirectory() as directory:
                log = Path(directory)/'worker.log'
                queue=Queue()
                for event in (10, 100, 'DONE'):
                    queue.put(event)
                with log.open('w', encoding='utf-8') as stream, redirect_stdout(stream), patch(
                    'logging.FileHandler', side_effect=AssertionError('A second log handle would corrupt output on Windows')
                ):
                    print('Training output before progress')
                    log_progress_from_queue(queue, str(log))
                    print('Training output after progress')
                contents=log.read_text(encoding='utf-8')
                self.assertIn('Training output before progress',contents)
                self.assertIn('Progress: 10%',contents)
                self.assertIn('Progress: 100%',contents)
                self.assertIn('Process completed.',contents)
                self.assertIn('Training output after progress',contents)
        finally:
            sys.path.pop(0)

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
