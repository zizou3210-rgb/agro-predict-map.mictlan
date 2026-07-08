"""Run a genetic algorithm for optimization
    """

import random
import copy
from typing import Tuple, List
from queue import Queue
import joblib

import pandas as pd

from featurehero.services.optimizations.optimization_enum import (
    GeneticAlgorithmParameter,
)
from featurehero.core.files.machine_file import (
    FileMachine,
    DatasetOptimizationData,
)
from featurehero.services.machines.machine_build import (
    machine_build_regression_optimization_decimal,
)
from featurehero.services.machines.machine import MachineRegression
from featurehero.core.metrics.metric import Metric
from featurehero.core.metrics.metric_enums import MetricEnum
from featurehero.services.machines.machine_enums import MachineNames
from featurehero.core.result_genetic import create_graph_model_index


class GeneticIndividual:
    """Class to create a individual for genetic algorithm"""

    def __init__(
        self,
        machine: MachineRegression = None,
        metric_selection: MetricEnum = None,
    ) -> None:
        self._dataset: DatasetOptimizationData = None
        self._machine = None
        if machine is not None:
            self._machine = machine
        self._features_chromosome: list[bool] = None
        self._metric: Metric = None
        self._index_metric: float = None
        self._metric_selection = None
        if metric_selection is not None:
            self._metric_selection = metric_selection

    def __str__(self) -> str:
        return f"machine: {
            self._machine
        }  features: {
            self._dataset.features_name_that_be_true
        }"

    @property
    def dataset(self):
        """Get the dataset"""
        return self._dataset

    @property
    def machine(self) -> MachineRegression:
        """Get the machine"""
        if self._machine is None:
            raise ValueError("Machine is not defined")
        return self._machine

    @property
    def index_metric(self) -> float:
        """Get the index metric"""
        return self._index_metric

    @property
    def features_chromosome(self):
        """Get the features chromosome"""
        return self._features_chromosome

    def run(self):
        """Run the machine with the features selected"""
        self._machine.build_machine()
        self._machine.training(
            x_train=self._dataset.x_train,
            y_train=self._dataset.y_train,
        )
        self._metric = self._machine.test(
            x_test=self._dataset.x_test,
            y_test=self._dataset.y_test,
        )
        if self._metric_selection is None:
            raise ValueError("Metric selection is not defined")
        self._index_metric = self._metric.get_single_metric(
            metric=self._metric_selection
        )

    def set_features_chromosome(self, features_chromosome: list[bool]):
        """Set the features chromosome"""
        if True not in features_chromosome:
            features_chromosome[random.randrange(
                len(features_chromosome))] = True
        self._features_chromosome = features_chromosome

    def set_machine(self, machine: MachineRegression):
        """Set the machine"""
        self._machine = machine

    def set_metric_selection(self, metric_selection: MetricEnum):
        """Set the metric selection"""
        self._metric_selection = metric_selection

    def apply_dataset(
        self,
        file_machine: FileMachine,
        features_chromosome: list[bool] = None,
    ):
        """Convert the features chromosome to dataset

        Args:
            file_machine (FileMachine): file with all information from dataset
            features_chromosome (list[bool], optional): Features chromosome to
                define the columns to keep. Defaults to None.

        Raises:
            ValueError: Error if not was define features chromosome.
        """
        if features_chromosome is not None:
            self.set_features_chromosome(
                features_chromosome=features_chromosome)
        if self._features_chromosome is None:
            raise ValueError("Features chromosome is not defined")
        self.set_features_chromosome(
            features_chromosome=[
                random.choice([True, False]) for _ in self._features_chromosome
            ]
        )
        self._dataset = file_machine.get_dataset(
            columns_to_keep=self._features_chromosome
        )

    def mutate_features_chromosome(
        self,
        mutation_rate: float,
    ) -> None:
        """Mutate the features chromosome

        Args:
            rate_mutation (float): Range between 0 and 1 to
                mutate the chromosome
        """
        self.set_features_chromosome(
            features_chromosome=[
                (not feature if random.random() < mutation_rate else feature)
                for feature in self._features_chromosome
            ]
        )

    def free_memory(self):
        """Clean memory of the individual when it ready finish
        """
        self._dataset = None
        self._metric.free_memory()

    def to_dictionary(self, features_names: list[str]) -> dict:
        """Convert the individual to dictionary

        Returns:
            dict: Dictionary with the individual information
        """
        general_dict = {
            "machine_name": self._machine.machine_name,
            "index_metric": self._index_metric,
        }
        general_dict.update(self._metric.get_all_metric())
        for key in self._machine.hyper_parameters:
            new_key = f"{key}_{self._machine.machine_name}"
            general_dict[new_key] = self._machine.hyper_parameters[key].value
        for chromosome, feature in zip(
            self._features_chromosome, features_names
        ):
            general_dict[f"feature_{feature}"] = chromosome
        return general_dict


class LogGenetic:
    """Class to log the genetic algorithm"""

    def __init__(
        self,
        number_generation: int,
        number_population: int,
        progress_queue: Queue,
        number_machines: int,
    ) -> None:
        self._message = ""
        self._number_generation = number_generation
        self._number_population = number_population
        self._progress_queue = progress_queue
        self._number_split_machines = 100 / number_machines

    def _call_progress(
        self,
        generation_number: int,
        current_machine: int,
    ) -> None:
        """Call the progress"""
        progress_float = (
            (self._number_split_machines * current_machine) * generation_number
        ) / 100
        progress = int(round(progress_float))
        if progress > 100:
            progress = 100
        if self._progress_queue is not None:
            self._progress_queue.put(progress)

    def progress_log(
        self,
        generation_number: int,
        current_machine: int,
    ):
        """Log of the generation"""
        message = f"Progress: {
            generation_number / self._number_generation
        }"
        self.adding_message(
            message=message,
        )
        self._call_progress(
            generation_number=generation_number,
            current_machine=current_machine,
        )
        self.log_message()

    def initial_log(self):
        """Initial log of algorithm"""
        self.adding_message(message="Starting the genetic algorithm")
        self.adding_message(message=f"population: {self._number_population}")
        self.adding_message(message=f"generations: {self._number_generation}")
        self.log_message()

    def adding_message(self, message: str, prefix: bool = False) -> None:
        """Adding message to the optimization

        Args:
            message (str): Message to store
            prefix (bool, optional): If True, concatenate the message;
                otherwise, overwrite it. Defaults to False.
        """

        if prefix is False:
            self._message = f"{self._message} {message}"
        else:
            self._message = f"{message} {self._message}"

    def log_message(self, quick_message: str = None) -> None:
        """Log the message"""
        if quick_message is not None:
            print(quick_message)
        else:
            print(self._message)
            self._message = ""

    def selection_log(self, number_individual: int, machine_name: str):
        """Log the selection"""
        self.adding_message(message=f"Individual {number_individual} ")
        self.adding_message(message=f" machine {machine_name} ")
        self.adding_message(message=f" - {self._number_population} ")
        self.log_message()


class GeneticAlgorithm:
    """Main class to run the genetic algorithm for optimization process."""

    def __init__(
        self,
        file_machine: FileMachine,
        genetic_algorithm_parameters: GeneticAlgorithmParameter,
        features_references: str,
        progress_queue: Queue,
        status_file: str | None = None,
    ) -> None:
        self._file_machine = file_machine
        self._genetic_parameters = genetic_algorithm_parameters
        self._population: list[GeneticIndividual] = []
        self._new_population: list[GeneticIndividual] = []
        self._global_population: list[GeneticIndividual] = []
        self._status_file = status_file
        self._log = LogGenetic(
            number_generation=self._genetic_parameters.number_generation,
            number_population=self._genetic_parameters.number_population,
            progress_queue=progress_queue,
            number_machines=len(self._genetic_parameters.machines_key),
        )
        self._current_generation_number = 0
        self._features_references = "".join(
            features_references.split()).split(",")

    def _write_status(self, current_step: int, total_steps: int):
        """Writes the current progress to the status file."""
        if self._status_file:
            try:
                with open(self._status_file, "w", encoding="utf-8") as f:
                    f.write(f"{current_step}/{total_steps}")
            except IOError as e:
                # It's better not to crash the whole process
                # for a status update
                print(f"Warning: Could not write to status file "
                      f"{self._status_file}: {e}")

    def _create_initial_population(
        self,
        population_number: int,
        machines: List[MachineNames],
    ) -> None:
        """Create the initial population"""
        self._population.clear()
        for _ in range(population_number):
            self._population.append(
                self._create_initial_individual(
                    features=self._file_machine.columns_name_with_out_target,
                    machines=machines,
                )
            )
        self._population[0] = self._update_features_from_reference(
            individual=self._population[0]
        )

    def _update_features_from_reference(
        self, individual: GeneticIndividual
    ) -> GeneticIndividual:
        """Create a one individual take a sort configuration

        Returns:
            GeneticIndividual: _description_
        """
        if len(self._features_references) == 0:
            return individual
        features = []
        for name in self._file_machine.columns_name_with_out_target:
            allele = False
            if name in self._features_references:
                allele = True
            features.append(allele)
        individual.set_features_chromosome(features_chromosome=features)
        return individual

    def _create_initial_individual(
        self,
        features: List[str],
        machines: List[MachineNames] = None,
    ) -> GeneticIndividual:
        """Create a individual with the features selected

        Args:
            features (list[str]): list of columns of dataset

        Returns:
            GeneticIndividual: Individual with the features
                selected and one machine by random
        """
        machines_chose = self._genetic_parameters.machines_key
        if machines is not None and len(machines) != 0:
            machines_chose = machines
        genetic_individual = GeneticIndividual(
            machine=machine_build_regression_optimization_decimal(
                machine_name=random.choice(machines_chose),
                deep_decimal=self._genetic_parameters.deep_decimal,
                metric_selection=self._genetic_parameters.metric_selection,
            ),
            metric_selection=self._genetic_parameters.metric_selection,
        )
        feature_chromosome = [random.choice([True, False]) for _ in features]
        if True not in feature_chromosome:
            feature_chromosome[random.randrange(
                len(feature_chromosome))] = True

        genetic_individual.apply_dataset(
            file_machine=self._file_machine,
            features_chromosome=feature_chromosome,
        )
        return genetic_individual

    def _crossover_features(
        self,
        parent_1: GeneticIndividual,
        parent_2: GeneticIndividual,
    ) -> Tuple[GeneticIndividual, GeneticIndividual]:
        """Create a cross of features

        Returns:
            Tuple[GeneticIndividual,
                GeneticIndividual]: 2 child for new generation
        """
        crossover_point = random.randint(
            1, len(self._file_machine.columns_name_with_out_target) - 1
        )
        child_1 = GeneticIndividual(
            metric_selection=self._genetic_parameters.metric_selection
        )
        child_2 = GeneticIndividual(
            metric_selection=self._genetic_parameters.metric_selection
        )
        child_1_features_chromosome = (
            parent_1.features_chromosome[:crossover_point]
            + parent_2.features_chromosome[crossover_point:]
        )
        child_2_features_chromosome = (
            parent_2.features_chromosome[:crossover_point]
            + parent_1.features_chromosome[crossover_point:]
        )

        child_2.set_features_chromosome(child_2_features_chromosome)
        child_1.set_features_chromosome(child_1_features_chromosome)
        return (child_1, child_2)

    def _crossover(
        self,
        parent_1: GeneticIndividual,
        parent_2: GeneticIndividual,
    ):
        """Crossover between two parents"""
        child_1, child_2 = self._crossover_features(
            parent_1=parent_1,
            parent_2=parent_2,
        )
        if parent_1.machine.machine_name == parent_2.machine.machine_name:
            crossover_point = random.randint(
                1, len(parent_1.machine.hyper_parameters) - 1
            )
            hyper_parameters_child_1 = {}
            hyper_parameters_child_2 = {}
            index = 0
            for key_1, value_1 in parent_1.machine.hyper_parameters.items():
                key_2_value = parent_2.machine.hyper_parameters[key_1]
                if index >= crossover_point:
                    hyper_parameters_child_1[key_1] = value_1
                    hyper_parameters_child_2[key_1] = key_2_value
                else:
                    hyper_parameters_child_1[key_1] = key_2_value
                    hyper_parameters_child_2[key_1] = value_1
                index = index + 1
            parent_1.machine.set_hyper_parameters(hyper_parameters_child_1)
            child_1.set_machine(parent_1.machine)
            parent_2.machine.set_hyper_parameters(hyper_parameters_child_2)
            child_2.set_machine(parent_2.machine)
        else:
            child_1.set_machine(parent_1.machine)
            child_2.set_machine(parent_2.machine)
            child_2.machine.force_mutate_hyper_parameters(
                deep_decimal=self._genetic_parameters.deep_decimal
            )
            cross_over_rate = self._genetic_parameters.get_cross_over_rate(
                self._current_generation_number)
            if random.random() < cross_over_rate:
                child_1.machine.force_mutate_hyper_parameters(
                    deep_decimal=self._genetic_parameters.deep_decimal
                )
        return child_1, child_2

    def _stop_genetic_algorithm(
        self,
    ) -> bool:
        """check if the algorithm need to stop

        Args:
            current_population (List): _description_

        Returns:
            bool: _description_
        """
        max_generations = self._genetic_parameters.number_generation
        if self._current_generation_number > max_generations:
            print("Stop by number of generations")
            return False
        if (len(self._population) > 0 and
                self._population[0].index_metric is not None):
            first = self._population[:10]
            for i in range(len(first) - 1):
                if abs(
                    first[i].index_metric - first[i + 1].index_metric
                ) >= 0.1:
                    return True
            print("Stop by don't get better results")
            return False
        return True

    def run(self):
        """Main function to run the genetic algorithm"""
        total_generations = self._genetic_parameters.number_generation
        num_machines = len(self._genetic_parameters.machines_key)
        total_steps = total_generations * num_machines

        for machine_idx, machine in enumerate(
            self._genetic_parameters.machines_key
        ):
            current_machine = machine_idx + 1
            self._log.initial_log()
            self._create_initial_population(
                population_number=self._genetic_parameters.number_population,
                machines=[machine],
            )
            self._log.log_message(quick_message="Finish first population")
            self._current_generation_number = 1
            while self._stop_genetic_algorithm():
                current_step = (
                    (machine_idx * total_generations) +
                    self._current_generation_number)
                self._write_status(current_step, total_steps)
                self._log.progress_log(
                    generation_number=self._current_generation_number,
                    current_machine=current_machine,
                )
                self._selection()
                for i in range(
                    self._genetic_parameters.number_population // 2
                ):
                    child_1, child_2 = self._crossover(
                        parent_1=self._population[i],
                        parent_2=self._population[
                            self._genetic_parameters.number_population - 1
                        ],
                    )
                    child_1, child_2 = self._mutation_two_children(
                        child_1=child_1,
                        child_2=child_2,
                    )
                    self._new_population.append(child_1)
                    self._new_population.append(child_2)
                self._store_population()
                if self._current_generation_number % 10 == 0:
                    self.export()
                self._current_generation_number = (
                    self._current_generation_number + 1
                )

    def _mutation_two_children(
        self, child_1: GeneticIndividual, child_2: GeneticIndividual
    ) -> Tuple[GeneticIndividual, GeneticIndividual]:
        """Mutation of the population

        Args:
            child_1 (GeneticIndividual): First child
            child_2 (GeneticIndividual): Second child

        Returns:
            _type_: return 2 child
        """
        mutation_rate = self._genetic_parameters.get_mutation_rate(
            number_generation=self._current_generation_number
        )
        deep_decimal = self._genetic_parameters.deep_decimal

        child_1.mutate_features_chromosome(mutation_rate=mutation_rate)
        child_2.mutate_features_chromosome(mutation_rate=mutation_rate)

        child_1.apply_dataset(file_machine=self._file_machine)
        child_2.apply_dataset(file_machine=self._file_machine)

        child_1.machine.mutate_hyper_parameters(
            mutation_rate=mutation_rate, deep_decimal=deep_decimal)
        child_2.machine.mutate_hyper_parameters(
            mutation_rate=mutation_rate, deep_decimal=deep_decimal)

        return child_1, child_2

    def _selection(self):
        """Run every model in all population and sort by best metric"""
        for number_individual, individual in enumerate(self._population):
            self._log.selection_log(
                number_individual=number_individual,
                machine_name=individual.machine.machine_name,
            )
            individual.run()
        self._population.sort(
            key=lambda individual: individual.index_metric,
            reverse=self._selection_reverse(),
        )

    def _selection_reverse(self) -> bool:
        """Get if the best model is the lowest or the highest

        Raises:
            ValueError: Model no define

        Returns:
            _type_: sort ascending or descending
        """
        if self._genetic_parameters.metric_selection in [
            MetricEnum.ACCURACY_MEAN_ABSOLUTE_PERCENTAGE_ERROR,
            MetricEnum.R2_SCORE,
        ]:
            return True
        if self._genetic_parameters.metric_selection in [
            MetricEnum.MEAN_ABSOLUTE_ERROR,
            MetricEnum.MEAN_SQUARED_ERROR,
        ]:
            return False
        raise ValueError("Metric not defined, to select the best model")

    def _store_population(self):
        """Store the population in a file"""
        data_population = copy.deepcopy(self._population)
        for individual in data_population:
            individual.free_memory()
        self._global_population.extend(data_population)
        self._population = []
        self._global_population.sort(
            key=lambda individual: individual.index_metric,
            reverse=self._selection_reverse(),
        )
        self._population = copy.deepcopy(self._new_population)
        self._new_population = []

    def export(self):
        """Export the best individual"""
        metric_to_csv = []
        for individual in self._global_population:
            metric_dict = individual.to_dictionary(
                features_names=self._file_machine.columns_name_with_out_target,
            )
            metric_to_csv.append(metric_dict)
        data_frame_metric = pd.DataFrame(metric_to_csv)
        self._file_machine.storage_file.save_data_frame_to_csv(
            data_frame=data_frame_metric,
            prefix="optimization",
        )
        ten_percent = int(len(data_frame_metric) * 0.1)
        sampled_data_frame = data_frame_metric.sample(n=ten_percent)
        self._file_machine.storage_file.save_data_frame_to_csv(
            data_frame=sampled_data_frame,
            prefix="optimization_overlap",
        )
        file_save = (
            self._file_machine.storage_file.adding_prefix_file_name_only_file(
                prefix="optimization"
            )
        )
        create_graph_model_index(
            file_result=file_save,
            folder=self._file_machine.file_data.folder_path,
            prefix="optimization_overlap",
            limit_rows=int(len(data_frame_metric) * 0.05),
        )
        create_graph_model_index(
            file_result=file_save,
            folder=self._file_machine.file_data.folder_path,
            prefix="optimization",
        )
        model = self._global_population[0].machine
        save_path_model = (
            self._file_machine.storage_file.adding_prefix_name_extension(
                prefix="best_model",
                extension="pkl",
            )
        )
        joblib.dump(model, save_path_model)
        best_features = self._global_population[0].features_chromosome
        save_best_features = (
            self._file_machine.storage_file.adding_prefix_name_extension(
                prefix="best_features",
                extension="pkl",
            )
        )
        joblib.dump(best_features, save_best_features)
