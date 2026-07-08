""" All basic concepts and enums for work with genetics values"""
from typing import List, Dict

from abc import ABC
from dataclasses import dataclass, field
from enum import Enum

import pandas as pd

from featurehero.services.machines.machine_enums import (
    MachineNames,
    MachineDefaultDefinition,
    convert_str_to_machine_name,
    HyperParameterRebuild,
)
from featurehero.core.files.machine_file import (
    TrainingData,
    FileMachine,
    FileDataRegression,
)
from featurehero.core.metrics.metric_enums import MetricEnum
from featurehero.core.files.access_file import StorageFile


class GeneticIndividualParameter():
    """Parameter to create a individual for genetic algorithm
    """

    def __init__(
        self,
        number_population: int = 100,
        deep_decimal: int = 5,
        metric_selection: MetricEnum = (
            MetricEnum.ACCURACY_MEAN_ABSOLUTE_PERCENTAGE_ERROR
        ),
        machines_key: List[MachineNames] = None,
    ) -> None:
        self._number_population = number_population
        self._deep_decimal = deep_decimal
        self._metric_selection = metric_selection
        self._machines_key = [
            MachineNames.LASSO_REGRESSION,
            MachineNames.EXTREME_GRADIENT_BOOSTING_REGRESSION,
            MachineNames.RANDOM_FOREST_REGRESSION,
            MachineNames.SUPPORT_VECTOR_REGRESSION,
        ]
        if machines_key is not None:
            self._machines_key = machines_key

    @property
    def number_population(self) -> int:
        """Return the number of population"""
        return self._number_population

    @property
    def deep_decimal(self) -> int:
        """Return the deep decimal"""
        return self._deep_decimal

    @property
    def metric_selection(self) -> MetricEnum:
        """Return the metric selection"""
        return self._metric_selection

    @property
    def machines_key(self) -> List[MachineNames]:
        """Return the list of machines key"""
        return self._machines_key


@dataclass
class GeneticMutationParameter():
    """Parameter to create a mutation for genetic algorithm
    """
    mutation_rate: float = 0.05
    cross_over_rate: float = 0.8


@dataclass
class GeneticAlgorithmParameter(ABC):
    """Configuration to run the genetic algorithm
    """

    def __init__(self, params: dict = None) -> None:
        self._number_generation: int = 100
        self._individual_parameter = GeneticIndividualParameter(
            number_population=80,
            metric_selection=MetricEnum.R2_SCORE,
        )
        self._mutation_parameters = [
            GeneticMutationParameter(
                cross_over_rate=0.8,
                mutation_rate=0.8,
            ),
            GeneticMutationParameter(
                cross_over_rate=0.4,
                mutation_rate=0.4,
            ),
            GeneticMutationParameter(
                cross_over_rate=0.2,
                mutation_rate=0.2,
            ),
        ]
        self._training_data = TrainingData()
        if params is not None:
            valid_params = {
                "number_generation",
                "number_population",
                "machines",
                "metric",
            }
            for param in params:
                if param not in valid_params:
                    raise ValueError(f"Invalid parameter: {param}")

            if "number_generation" in params:
                self._number_generation = params["number_generation"]
            if "number_population" in params:
                # pylint: disable=protected-access
                self._individual_parameter._number_population = params[
                    "number_population"
                ]
            if "machines" in params:
                # pylint: disable=protected-access
                self._individual_parameter._machines_key = [
                    convert_str_to_machine_name(machine_name)
                    for machine_name in params["machines"]
                ]
            if "metric" in params:
                # pylint: disable=protected-access
                self._individual_parameter._metric_selection = MetricEnum(
                    params["metric"].lower()
                )

    @property
    def machines_key(self) -> List[MachineNames]:
        """Return the list of machines key

        Returns:
            list[MachineNames]: machines key
        """
        return self._individual_parameter.machines_key

    @property
    def number_population(self) -> int:
        """Return the population

        Returns:
            int: population
        """

        return self._individual_parameter.number_population

    @property
    def number_generation(self) -> int:
        """Return the number of generation


        Returns:
            int: number of generation
        """
        return self._number_generation

    def get_mutation_rate(self, number_generation: int) -> float:
        """Return the mutation rate

        Returns:
            float: mutation rate
        """
        return self._get_parameters_by_number_generation(
            number_generation=number_generation
        ).mutation_rate

    def _get_parameters_by_number_generation(
            self,
            number_generation: int,
    ) -> GeneticMutationParameter:
        """Return the mutation parameters

        Returns:
            GeneticMutationParameter: mutation parameters
        """
        if self._number_generation * .60 < number_generation:
            return self._mutation_parameters[0]
        if self._number_generation * .90 < number_generation:
            return self._mutation_parameters[1]
        return self._mutation_parameters[2]

    def get_cross_over_rate(
            self, number_generation: int,
    ) -> float:
        """Return the cross over rate

        Returns:
            float: cross over rate
        """
        return self._get_parameters_by_number_generation(
            number_generation=number_generation
        ).cross_over_rate

    @property
    def deep_decimal(self) -> int:
        """Return the deep decimal

        Returns:
            int: deep decimal
        """
        return self._individual_parameter.deep_decimal

    @property
    def metric_selection(self) -> MetricEnum:
        """Return the metric selection

        Returns:
            MetricEnum: metric selection
        """
        return self._individual_parameter.metric_selection

    @property
    def training_data(self) -> TrainingData:
        """Return the training data

        Returns:
            TrainingData: training data
        """
        return self._training_data


class ActionProcedure(Enum):
    """Action on Forward Backward method
    """
    FORWARD = 'forward'
    BACKWARD = 'backward'
    COMBINATION = "combination"


class FeatureModeEnum(Enum):
    """ Type of feature
    """
    LIST = 1


@dataclass
class SelectionProcedure:
    """Class to define de action to do in the process
    """
    action: ActionProcedure
    metric: MetricEnum
    models: List[MachineDefaultDefinition]
    features: List[str] = field(default_factory=[])


class FileProcessFeatureSelection:

    """ Prepare all files and data to process for Forward and Backward"""

    def __init__(
        self,
        file_json_definition: str,
        file_name: str,
        folder: str,
    ):
        self._store_file = StorageFile(file_name=file_name, folder_file=folder)
        self._data_frame = self._store_file.get_csv_to_data_frame()
        definitions = self._store_file.get_json_from_file(
            file_name=file_json_definition,
        )
        self._file_machine = FileMachine(
            file_data=FileDataRegression(
                file_in=file_name,
                target_feature=definitions["target_feature"],
                folder_path=folder,
            ),
            training_data=TrainingData(),
        )
        self._procedure = self._find_procedure(data=definitions)

    def get_data_frame(self, features: List[str]) -> pd.DataFrame:
        """Return initial data frame

        Returns:
            pd.DataFrame: data frame filter by initial rows
        """
        return self._data_frame[features]

    def _find_procedure(self, data: Dict) -> SelectionProcedure:
        """Extract from dictionary the procedure

        Args:
            data (Dict): Data to extract

        Raises:
            KeyError: Some key dont exist

        Returns:
            ProcedureForwardBackward: return procedure
        """
        try:
            models: List[MachineDefaultDefinition] = []
            if "models" not in data:
                raise KeyError("All procedure need a list of models")
            for model_data in data["models"]:
                machine_name = convert_str_to_machine_name(model_data["name"])
                hyper_parameters = []
                if "hyper_parameters" in model_data:
                    for hyper_parameter_data in model_data["hyper_parameters"]:
                        hyper_parameters.append(HyperParameterRebuild(
                            name=hyper_parameter_data["name"],
                            value=hyper_parameter_data["value"],
                        ))
                models.append(
                    MachineDefaultDefinition(
                        machine_name=machine_name,
                        rebuild_hyper_parameters=hyper_parameters,
                    )
                )
            if "features" not in data:
                raise KeyError("All procedure need a list of feature")
            features = self._find_features(
                data=data,
            )
            return SelectionProcedure(
                action=ActionProcedure(data["action"].lower()),
                metric=MetricEnum(data["metric"].lower()),
                models=models,
                features=features,
            )
        except Exception as e:
            raise KeyError(f"Can't extract the procedure from f{e}") from e

    def _find_features(
            self,
            data: Dict,
    ) -> List[str]:
        """Find a feature by type ofg feature

        Args:
            data (Dict): data to get information
            case_feature (FeatureTypeEnum): tow types init, selection

        Returns:
            ProcedureFeature: return feature procedure
        """
        feature_dict = data["features"]
        features = []
        if "elements" in feature_dict:
            for feature_definition in feature_dict["elements"]:
                features = features + self._find_feature(
                    pattern=feature_definition["pattern"],
                    value=feature_definition["value"],
                )
        return features

    def _find_feature(self, pattern: str, value: str) -> List[str]:
        """Search and get features by patterns

        Args:
            pattern (str): patter to search
            value (str): value to search

        Returns:
            List[str]: list of features
        """
        if pattern.lower() == "like":
            return [column for column in self._data_frame.columns
                    if value.lower() in column.lower()
                    ]
        if pattern.lower() == "equal":
            if value in self._data_frame.columns:
                return [value]
        raise KeyError(f"Pattern {pattern} or column {value} don't exist")

    @property
    def store_file(self) -> StorageFile:
        """To operate with main file

        Returns:
            StorageFile: Return storage file
        """
        return self._store_file

    @property
    def file_machine(self) -> FileMachine:
        """Get the file data regression and target column

        Returns:
            FileDataRegression: file data
        """
        return self._file_machine

    @property
    def procedure(self) -> SelectionProcedure:
        """Get current procedure action

        Returns:
            ProcedureForwardBackward: current procedure
        """
        return self._procedure
