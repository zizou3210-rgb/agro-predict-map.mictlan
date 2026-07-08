"""Function to fill NAN or empty values"""

import pandas as pd
from src.helpers.file_access import get_file_to_data_frame, FolderList, save_to_csv


def missing_by_mean_for_features(file_in: str, folder_file=FolderList.UPLOAD) -> None:
    """Fill all data in every feature (column) by mean of this column

    Args:
        file_in (str): file to fill
        folder_file (str): folder to put the data in
    """
    df = get_file_to_data_frame(file_name=file_in, folder=folder_file)

    for col_name in df.columns:
        if df[col_name].dtype == object:
            original_values_not_null = df[col_name].notnull()
            coerced_values_are_null = pd.to_numeric(
                df[col_name], errors='coerce').isnull()
            if (original_values_not_null & coerced_values_are_null).any():
                raise TypeError(f"The column {col_name} can not be a str.")

    df.fillna(df.mean(), inplace=True)
    file_save = f"fill_avg_{file_in}"
    save_to_csv(data_frame=df, file_save=file_save)
