"""Function to use in other class"""
import os
import json
import random
import re
from dataclasses import dataclass


import pandas as pd
from featurehero.core.key_env import (
    IS_DEBUG,
)


@dataclass
class FileData():
    """ Minimal parameter for file"""
    file_in: str
    folder_path: str

    def re_sort_columns(
        self,
        importance_columns_str: str,
    ) -> None:
        """Open file and change the order of columns"""
        importance_columns = [
            re.sub(r'^[ \n\r\t]+', '', element) for element in
            importance_columns_str.split(',')
        ]
        storage_file = StorageFile(
            file_name=self.file_in,
            folder_file=self.folder_path,
        )
        df = storage_file.get_csv_to_data_frame()
        columns_of_df = list(df.columns)
        column_order = []
        column_rest = columns_of_df[:]
        for col in importance_columns:
            if col in columns_of_df:
                column_order.append(col)
                column_rest.remove(col)
        random.shuffle(column_rest)
        columns_final_order = column_order + column_rest
        df_sort = df.reindex(columns=columns_final_order)
        prefix = "sort"
        storage_file.save_data_frame_to_csv(
            data_frame=df_sort,
            prefix=prefix,
        )
        self.file_in = \
            storage_file.adding_prefix_file_name_only_file(prefix=prefix)


class StorageFile():
    """Convert file in access class to get it
    """

    def __init__(
            self,
            file_name: str,
            folder_file: str,
    ):
        self.folder_file = folder_file
        self.file_name = file_name
        self.work_folder = os.path.join(
            folder_file)
        self.absolute_file = os.path.join(
            folder_file, file_name)
        self.file_name_only, _ = os.path.splitext(self.file_name)

    def get_json_from_file(self, file_name: str, ) -> dict:
        """Util - load json str to json dictionary """
        file = os.path.join(self.work_folder, file_name)
        if IS_DEBUG:
            print(os.getcwd())
            print(self.work_folder)
            print(file)
        if os.path.isfile(file):
            json_dict = None
            with open(file, 'r', encoding="utf-8") as f:
                json_dict = json.load(f)
            return json_dict
        raise FileNotFoundError(f"file not found - {file}")

    def adding_prefix_file_name(self, prefix: str) -> str:
        """Adding one prefix to file to save on same folder keep
            the same extension

        Args:
            prefix (str): prefix of name

        Returns:
            str: absolute path to save file
        """
        return os.path.join(
            self.work_folder,
            f"{prefix}_{self.file_name}",
        )

    def adding_prefix_file_name_only_file(self, prefix: str) -> str:
        """Adding one prefix to file to save on same folder keep
            the same extension, but only return file

        Args:
            prefix (str): prefix of name

        Returns:
            str: absolute path to save file
        """
        return os.path.join(f"{prefix}_{self.file_name}")

    def adding_prefix_name_extension(self, prefix: str,
                                     extension: str) -> str:
        """Adding one prefix to file to save on same folder keep
            with other extension

        Args:
            prefix (str): prefix of name

        Returns:
            str: absolute path to save file
        """
        return os.path.join(
            self.work_folder,
            f"{prefix}_{self.file_name_only}.{extension}",
        )

    def adding_file_to_work_directory(self, file_name: str) -> str:
        """Adding new file on same folder that file original work

        Args:
            file_name (str): return the name with absolute path

        Returns:
            str: path and file
        """
        return os.path.join(self.work_folder, file_name)

    def save_data_frame_to_csv(self, data_frame: pd.DataFrame,
                               prefix: str,
                               is_index: bool = False) -> None:
        """Save some data frame on same folder with a prefix

        Args:
            data_frame (pd.DataFrame): _description_
            file_save (str): _description_
            is_index (bool, optional): _description_. Defaults to False.
        """
        path_to_save = self.adding_prefix_file_name(prefix=prefix)
        data_frame.to_csv(path_to_save, index=is_index)

    def get_csv_to_data_frame(self, other_file: str = "") -> pd.DataFrame:
        """Get some file to data frame, if nor file is passing
            get the main file

        Args:
            other_file (str, optional): Other file to get. Defaults to "".

        Returns:
            pd.DataFrame: Data frame
        """
        file = self.absolute_file
        if other_file != "":
            file = other_file
        if IS_DEBUG:
            print(os.getcwd())
            print(self.work_folder)
            print(file)
        if os.path.isfile(file):
            return pd.read_csv(file)
        raise FileNotFoundError(f"file not found - {file}")
