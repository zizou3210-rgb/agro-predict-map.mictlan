"""Work with outliers """

from src.helpers.file_access import FolderList, StorageFile, FileInformation
from src.outliers.outlier_columns import (
    get_outlier_zscore_new_column,
    remove_column_by_zscore,
)


def remove_outlier_by_zscore(
    file_name: str,
    target_column: str,
    folder: FolderList = FolderList.UPLOAD,
    outlier_threshold: float = 3.0,
):
    """Remove outliers by zscore on file

    Args:
        file_name (str): file name
        target_column (str): column target
    """
    file_information = FileInformation(_file_name=file_name, _file_folder=folder)
    store_file = StorageFile(file_information=file_information)
    df = store_file.get_csv_to_data_frame()
    df_zscore = get_outlier_zscore_new_column(df, target_column)
    store_file.save_data_frame_to_csv(data_frame=df_zscore, prefix="outlier_zscore")
    remove_outlier_zscore = remove_column_by_zscore(
        df, target_column, outlier_threshold
    )
    store_file.save_data_frame_to_csv(
        data_frame=remove_outlier_zscore, prefix="remove_outlier_zscore"
    )
