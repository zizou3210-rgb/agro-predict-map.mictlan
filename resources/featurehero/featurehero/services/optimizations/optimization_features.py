"""Techniques for selection best features by models """

from typing import List, Dict
import copy
import itertools

import pandas as pd

from featurehero.services.optimizations.optimization_enum import (
    FileProcessFeatureSelection, ActionProcedure
)
from featurehero.services.machines.machine_build import (
    build_machine_regression
)
from featurehero.services.machines.machine import MachineRegression


class FeatureSelection:
    """Run the backward feature selection and whe it finish
        run the forward feature selection
    """

    def __init__(
        self,
        file_process: FileProcessFeatureSelection,
    ) -> None:
        self._procedure = file_process.procedure
        self._file_machine = file_process.file_machine
        self._store_file = file_process.store_file
        self._result_dictionary = []

    def run(self) -> None:
        """Run the backward feature selection and whe it finish run
        the forward feature selection
        """
        if self._procedure.action == ActionProcedure.BACKWARD:
            self._backward_feature_selection()
        if self._procedure.action == ActionProcedure.COMBINATION:
            self._combination_feature_selection()

    def export(self) -> None:
        """Save all results
        """
        result = copy.deepcopy(self._result_dictionary)
        result.sort(key=lambda element: element["metric_index"], reverse=True)
        prefix = ""
        if self._procedure.action == ActionProcedure.BACKWARD:
            prefix = "result_backward"
        if self._procedure.action == ActionProcedure.COMBINATION:
            prefix = "result_combination"
        df = pd.DataFrame(result)
        self._store_file.save_data_frame_to_csv(
            data_frame=df,
            prefix=prefix
        )

    def _backward_feature_selection(
            self,
    ) -> None:
        """Run the backward feature selection
        """
        features_chromosome = (
            self._file_machine.cast_features_to_chromosome(
                features=self._procedure.features
            )
        )
        list_models = [m.machine_name.value for m in self._procedure.models]

        for model in self._procedure.models:
            print(f"Start with model {model.machine_name.value} "
                  f"from {list_models}")
            machine = build_machine_regression(
                machine_name=model.machine_name
            )
            if len(model.rebuild_hyper_parameters) > 0:
                machine.set_rebuild_hyper_parameters(
                    rebuild_parameters=model.rebuild_hyper_parameters
                )
            self._run_model_backward(
                features_chromosome=features_chromosome,
                machine=machine,
            )

    def _run_model_backward(
            self,
            features_chromosome: List[bool],
            machine: MachineRegression,
    ) -> None:
        """Run one model with all combination features

        Args:
            features (List[bool]): List of features
            machine (MachineRegression): machine to run
        """
        data_set = self._file_machine.get_dataset(
            columns_to_keep=features_chromosome,
        )
        machine.build_machine_default()
        machine.training(
            x_train=data_set.x_train,
            y_train=data_set.y_train,
        )
        metric = machine.test(
            x_test=data_set.x_test,
            y_test=data_set.y_test,
        )
        best_metric = metric.get_single_metric(
            metric=self._procedure.metric,
        )
        best_features_chromosome = copy.deepcopy(features_chromosome)
        self._result_dictionary.append(
            self._get_id_to_save(
                machine=machine,
                features_chromosome=best_features_chromosome,
                metrics=metric.get_all_metric(),
                metric_index=best_metric,
            )
        )

        for index, value in enumerate(features_chromosome):
            if value is True:
                machine.build_machine_default()
                best_features_chromosome[index] = False
                data_set = self._file_machine.get_dataset(
                    columns_to_keep=best_features_chromosome,
                )
                machine.build_machine_default()
                machine.training(
                    x_train=data_set.x_train,
                    y_train=data_set.y_train,
                )
                metric = machine.test(
                    x_test=data_set.x_test,
                    y_test=data_set.y_test,
                )
                single_metric = metric.get_single_metric(
                    metric=self._procedure.metric,
                )
                self._result_dictionary.append(
                    self._get_id_to_save(
                        machine=machine,
                        features_chromosome=best_features_chromosome,
                        metric_index=single_metric,
                        metrics=metric.get_all_metric(),
                    )
                )
                if best_metric < single_metric:
                    best_metric = single_metric
                else:
                    best_features_chromosome[index] = True

    def _get_id_to_save(
            self,
            machine: MachineRegression,
            features_chromosome: List[bool],
            metrics: Dict,
            metric_index: float,
    ) -> Dict:
        dictionary_id = {
            "machine_name": machine.machine_name,
            "time_training": machine.time_training,
        }
        if machine.rebuild_hyper_parameters is not None:
            for rebuild_hyper_parameter in machine.rebuild_hyper_parameters:
                key_id = (f"{rebuild_hyper_parameter.name}_"
                          f"{machine.machine_name}")
                dictionary_id[key_id] =\
                    rebuild_hyper_parameter.value
        for chromosome, feature in zip(
            features_chromosome,
            self._file_machine.columns_name_with_out_target
        ):
            dictionary_id[f"feature_{feature}"] = chromosome
        for key, value in metrics.items():
            dictionary_id[f"metric_{key}"] = value
        dictionary_id["metric_index"] = metric_index
        return dictionary_id

    def _combination_feature_selection(self) -> None:
        """Run all possible combination of variables
        """
        features_chromosome = (
            self._file_machine.cast_features_to_chromosome(
                features=self._procedure.features
            )
        )
        list_models = [m.machine_name.value for m in self._procedure.models]
        for model in self._procedure.models:
            print(f"Start with model {model.machine_name.value} "
                  f"from {list_models}")
            machine = build_machine_regression(
                machine_name=model.machine_name
            )
            if len(model.rebuild_hyper_parameters) > 0:
                machine.set_rebuild_hyper_parameters(
                    rebuild_parameters=model.rebuild_hyper_parameters
                )
            self._run_model_combination(
                features_chromosome=features_chromosome,
                machine=machine,
            )

    def _run_model_combination(
            self,
            features_chromosome: List[bool],
            machine: MachineRegression,
    ) -> None:
        """Run one model with all combination features

        Args:
            features (List[bool]): List of features
            machine (MachineRegression): machine to run
        """
        combinations = self._generate_combination_true_with_all_false(
            features_chromosome=features_chromosome
        )
        for current_chromosome in combinations:
            machine.build_machine_default()
            data_set = self._file_machine.get_dataset(
                columns_to_keep=current_chromosome,
            )
            machine.build_machine_default()
            machine.training(
                x_train=data_set.x_train,
                y_train=data_set.y_train,
            )
            metric = machine.test(
                x_test=data_set.x_test,
                y_test=data_set.y_test,
            )
            single_metric = metric.get_single_metric(
                metric=self._procedure.metric,
            )
            self._result_dictionary.append(
                self._get_id_to_save(
                    machine=machine,
                    features_chromosome=current_chromosome,
                    metric_index=single_metric,
                    metrics=metric.get_all_metric(),
                )
            )

    def _generate_combination_true_with_all_false(self, features_chromosome):
        """
        Generate all combinations with at least one True value.

        This returns the complete array with combinations of True converted
        to False, but without returning arrays with only False values.

        Args:
            features_chromosome (list): The input boolean array.

        Yields:
            list: The boolean array modified with a combination of True
            values converted to False.
        """
        index_true = [i for i, value in
                      enumerate(features_chromosome) if value]

        if not index_true:
            return

        for long in range(1, len(index_true) + 1):
            for combination in itertools.combinations(index_true, long):
                feature_chromosome_edit = features_chromosome[:]
                for index in combination:

                    feature_chromosome_edit[index] = False

                if any(feature_chromosome_edit):
                    yield feature_chromosome_edit
