"""Operative class to run the genetic algorithm.
"""
from queue import Queue

from featurehero.services.optimizations.optimization_enum import (
    GeneticAlgorithmParameter,
    FileProcessFeatureSelection,
)
from featurehero.core.files.machine_file import FileDataRegression, FileMachine
from featurehero.services.optimizations.optimization_genetic_algorithm import (
    GeneticAlgorithm
)
from featurehero.services.optimizations.optimization_features import (
    FeatureSelection,
)


def optimization_run_from_task(
    file_data: FileDataRegression,
    importance_columns: str,
    progress_queue: Queue,
    params: dict = None,
    status_file: str | None = None,
) -> None:
    """Launch the genetic algorithm
    """
    if importance_columns != "" or importance_columns is not None:
        file_data.re_sort_columns(importance_columns_str=importance_columns)

    genetic_algorithm_parameters = GeneticAlgorithmParameter(params=params)
    genetic_algorithm = GeneticAlgorithm(
        file_machine=FileMachine(
            file_data=file_data,
            training_data=genetic_algorithm_parameters.training_data,
        ),
        genetic_algorithm_parameters=genetic_algorithm_parameters,
        features_references=importance_columns,
        progress_queue=progress_queue,
        status_file=status_file,
    )
    genetic_algorithm.run()
    genetic_algorithm.export()


def feature_selection_run(
    file_name: str,
    file_json_definition: str,
    folder: str,
) -> None:
    """Run the backward feature selection and whe it finish
        run the forward feature selection
    """
    file_process = FileProcessFeatureSelection(
        file_json_definition=file_json_definition,
        file_name=file_name,
        folder=folder,
    )
    features = FeatureSelection(
        file_process=file_process
    )
    features.run()
    features.export()
