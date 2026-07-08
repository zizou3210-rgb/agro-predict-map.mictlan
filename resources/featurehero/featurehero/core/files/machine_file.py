"""Work with data files for all machines """


from dataclasses import dataclass
from typing import List

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split

from featurehero.core.files.access_file import FileData, StorageFile


@dataclass
class FileDataRegression(FileData):
    """File information
    """
    target_feature: str


@dataclass
class TrainingData():
    """Data for create the training
    """
    test_size: float = 0.8
    random_state: int = 42


@dataclass
class DatasetOptimizationData:
    """All properties for get the file and pass to the machine
    """
    x: np.ndarray
    y: np.ndarray
    x_train: np.ndarray
    x_test: np.ndarray
    y_train: np.ndarray
    y_test: np.ndarray
    features_name_that_be_true: list[str] = None


class FileMachine():
    """Run all machines for Predicted
    """

    def __init__(
        self,
        file_data: FileDataRegression,
        training_data: TrainingData,
    ) -> None:
        self._file_data = file_data
        self._training_data = training_data
        self._storage_file = StorageFile(
            file_name=self._file_data.file_in,
            folder_file=self._file_data.folder_path,
        )
        self.original_df = self._storage_file.get_csv_to_data_frame()

    def cast_features_to_chromosome(self, features: List[str]) -> List[bool]:
        """Return a list of chromosome with a list of features

        Args:
            features (List[str]): list of feature names

        Returns:
            List[bool]: list of chromosome
        """
        chromosome = []
        for column in self.without_target:
            if column in features:
                chromosome.append(True)
            else:
                chromosome.append(False)
        return chromosome

    def get_dataset(
            self,
            columns_to_keep: list[bool] = None
    ) -> DatasetOptimizationData:
        """Get some column of the dataset

        Args:
            columns_to_keep (list[bool], optional):
                List of boolean values indicating
                 which columns to keep. Defaults to None.

        Returns:
            DatasetOptimizationData: The dataset with selected columns
        """
        x = self.without_target
        if columns_to_keep is not None:
            if len(columns_to_keep) != len(x.columns):
                raise ValueError(
                    "Length of columns_to_keep must match the number of "
                    "columns in the dataset")
            x = x.loc[:, columns_to_keep]
        y = self.only_target
        x_train, x_test, y_train, y_test = train_test_split(
            x, y, test_size=self._training_data.test_size,
            random_state=self._training_data.random_state,
        )
        return DatasetOptimizationData(
            x=x,
            y=y,
            x_train=x_train,
            x_test=x_test,
            y_train=y_train,
            y_test=y_test,
            features_name_that_be_true=list(x.columns)
        )

    @property
    def without_target(self) -> pd.DataFrame:
        """Get data frame without target columns

        Returns:
            pd.DataFrame: Data frame without target column
        """
        return self.original_df.drop(
            self._file_data.target_feature,
            axis=1,
        )

    @property
    def only_target(self) -> pd.DataFrame:
        """Get data frame only target column

        Returns:
            pd.DataFrame: Data frame with only target column
        """
        return self.original_df[self._file_data.target_feature]

    @property
    def columns_name_with_out_target(self) -> list:
        """Get all columns name without target

        Returns:
            list: List of columns
        """
        return list(self.without_target.columns)

    @property
    def file_data(self) -> FileDataRegression:
        """Get the file data
        """
        return self._file_data

    @property
    def training_data(self) -> TrainingData:
        """Get the training data
        """
        return self._training_data

    @property
    def storage_file(self) -> StorageFile:
        """Get the storage file
        """
        return self._storage_file
