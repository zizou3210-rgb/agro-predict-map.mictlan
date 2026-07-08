"""Function to use in other class"""
import os
import json
import warnings

import pandas as pd
from src.helpers.key_env import IS_DEBUG, FolderList, FOLDER_FILES_REPOSITORY, FileInformation


def get_file(file_name: str, folder: FolderList) -> str:
    """Get file from cache"""
    warnings.warn(
        "Deprecate from 2024.11.14. Using the class 'FileInfoData' inside it.",
        DeprecationWarning
    )
    file = os.path.join(FOLDER_FILES_REPOSITORY, folder.value, file_name)
    return file


def get_file_to_data_frame(file_name: str, folder: FolderList) -> pd.DataFrame:
    """Util - load csv file with pandas """
    warnings.warn(
        "Deprecate from 2024.11.14. Using the class 'FileInfoData' inside it.",
        DeprecationWarning
    )
    file = os.path.join(FOLDER_FILES_REPOSITORY, folder.value, file_name)
    if IS_DEBUG:
        print(os.getcwd())
        print(FOLDER_FILES_REPOSITORY)
        print(file)
    if os.path.isfile(file):
        return pd.read_csv(file)
    raise FileNotFoundError(f"file not found - {file}")


def get_file_to_json(file_name: str, folder: FolderList) -> pd.DataFrame:
    """Util - load json str to json dictionary """
    warnings.warn(
        "Deprecate from 2024.11.14. Using the class 'FileInfoData' inside it.",
        DeprecationWarning
    )
    file = os.path.join(FOLDER_FILES_REPOSITORY, folder.value, file_name)
    if IS_DEBUG:
        print(os.getcwd())
        print(FOLDER_FILES_REPOSITORY)
        print(file)
    if os.path.isfile(file):
        json_dict = None
        with open(file, 'r', encoding="utf-8") as f:
            json_dict = json.loads(f)
        return json_dict
    raise FileNotFoundError(f"file not found - {file}")


def get_absolute_file_to_data_frame(path_to_file: str) -> pd.DataFrame:
    """file access - load csv file with pandas from absolute file name """
    warnings.warn(
        "Deprecate from 2024.11.14. Using the class 'FileInfoData' inside it.",
        DeprecationWarning
    )
    if IS_DEBUG:
        print(os.getcwd())
        print(FOLDER_FILES_REPOSITORY)
        print(path_to_file)
    if os.path.isfile(path_to_file):
        return pd.read_csv(path_to_file)
    raise FileNotFoundError(f"file not found - {path_to_file}")


def save_to_csv(data_frame: pd.DataFrame, file_save: str, is_index: bool = False) -> None:
    """Util -  save any data frame on file """
    warnings.warn(
        "Deprecate from 2024.11.14. Using the class 'FileInfoData' inside it.",
        DeprecationWarning
    )
    path_to_save = get_file(file_name=file_save, folder=FolderList.UPLOAD)
    data_frame.to_csv(path_to_save, index=is_index)


def get_name_file_without_extension(file_name: str, folder: FolderList) -> str:
    """Return only name of file

    Args:
        file_name (str): file name
        folder (FolderCache): Folder location

    Returns:
        str: _description_
    """
    warnings.warn(
        "Deprecate from 2024.11.14. Using the class 'FileInfoData' inside it.",
        DeprecationWarning
    )
    file = os.path.join(FOLDER_FILES_REPOSITORY, folder.value, file_name)
    complete_name = os.path.basename(file)
    name = os.path.splitext(complete_name)
    return name[0]


class StorageFile():
    """Convert file in access class to get it
    """

    def __init__(
        self,
        file_information: FileInformation,
    ) -> None:
        self.file_information = file_information
        self.work_folder = os.path.join(
            FOLDER_FILES_REPOSITORY,
            self.file_information.folder_value,
        )
        self.absolute_file = os.path.join(
            FOLDER_FILES_REPOSITORY,
            self.file_information.folder_value,
            self.file_information.file_name
        )
        self.file_name_only, _ = os.path.splitext(self.absolute_file)
        for folder in FolderList:
            self.get_absolute_path_and_create_folder(folder=folder)

    def file_edit_prefix(self, prefix: str) -> str:
        """Adding one prefix to file to save on same folder keep the same extension

        Args:
            prefix (str): prefix of name

        Returns:
            str: absolute path to save file
        """
        return os.path.join(
            FOLDER_FILES_REPOSITORY,
            self.file_information.folder_value,
            f"{prefix}_{self.file_information.file_name}",
        )

    def file_edit_prefix_and_extension(self, prefix: str, extension: str) -> str:
        """Adding one prefix to file to save on same folder keep with other extension

        Args:
            prefix (str): prefix of name

        Returns:
            str: absolute path to save file
        """
        return os.path.join(
            FOLDER_FILES_REPOSITORY,
            self.file_information.folder_value,
            f"{prefix}_{self.file_name_only}.{extension}",
        )

    def get_file_on_work_directory(self, file_name: str) -> str:
        """Adding new file on same folder that file original work

        Args:
            file_name (str): return the name with absolute path

        Returns:
            str: path and file
        """
        warnings.warn(
            "Deprecate from 2024.11.24. Using the class 'get_file_on_files_repository' inside it.",
            DeprecationWarning
        )
        return os.path.join(self.work_folder, file_name)

    def get_file_on_files_repository(
            self,
            file_name: str,
            folder: FolderList = FolderList.UPLOAD
    ) -> str:
        """get absolute path from file into file repository

        Args:
            folder (FolderList): folder to get data
            file_name (str): file name

        Returns:
            str: return absolute path
        """
        return os.path.join(FOLDER_FILES_REPOSITORY, folder.value, file_name)

    def save_data_frame_to_csv(
            self,
            data_frame: pd.DataFrame,
            prefix: str,
            is_index: bool = False
    ) -> None:
        """Save some data frame on same folder with a prefix

        Args:
            data_frame (pd.DataFrame): _description_
            file_save (str): _description_
            is_index (bool, optional): _description_. Defaults to False.
        """
        path_to_save = self.file_edit_prefix(prefix=prefix)
        data_frame.to_csv(path_to_save, index=is_index)

    def get_csv_to_data_frame(self, other_file: str = "") -> pd.DataFrame:
        """Get some file to data frame, if nor file is passing get the main file

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
            print(FOLDER_FILES_REPOSITORY)
            print(file)
        if os.path.isfile(file):
            return pd.read_csv(file)
        raise FileNotFoundError(f"file not found - {file}")

    def get_absolute_path_and_create_folder(self, folder: FolderList) -> str:
        """Get absolute path to some folder, if folder don't exist create it

        Args:
            folder (FolderCache): folder

        Returns:
            str: str with absolute path
        """
        path = os.path.join(FOLDER_FILES_REPOSITORY, folder.value)
        if not os.path.exists(path=path):
            os.makedirs(path)
        return path
