"""All env and static variable for system"""
import os
from enum import Enum
from dataclasses import dataclass


from dotenv import load_dotenv

load_dotenv()

FOLDER_FILES_REPOSITORY = os.getenv('FOLDER_DATA', '../data/')
REDIS_BROKEN = os.getenv("REDIS_URL")
IS_DEBUG = bool(os.getenv('DEBUG_MODE', 'false'))
FolderList = Enum(
    'FolderCache', [
        ("UPLOAD", "upload_files"),
        ("TEMP", "temp")
    ]
)


@dataclass
class FileInformation():
    """Store the file and folder main to work on it
    """
    _file_name: str
    _file_folder: FolderList = FolderList.UPLOAD

    @property
    def folder_value(self) -> str:
        """Get value of folder
        """
        return self._file_folder.value

    @property
    def file_name(self) -> str:
        """Get the file name

        Returns:
            str: file name
        """
        return self._file_name
