"""Class to normalize data"""
from sklearn.preprocessing import MinMaxScaler, StandardScaler

from src.helpers.file_access import get_file_to_data_frame, FolderList, save_to_csv
from src.normalize.action_enums import NormalizeActionEnum


def normalize_dataset(
        file_in: str,
        folder_file: FolderList,
        avoid_columns: list,
        action: NormalizeActionEnum = NormalizeActionEnum.DEFAULT,
) -> None:
    """Function to normalize all dataset in base of action 

    Args:
        file_in (str): file to normalize
        folder_file (FolderCache): folder where is the file
        avoid_columns (list): list of column to avoid normalize
        action (NormalizeActionEnum, optional): action or type of normalize. 
            Defaults to NormalizeActionEnum.DEFAULT.
    """
    df = get_file_to_data_frame(file_name=file_in, folder=folder_file)
    if action == NormalizeActionEnum.MINUS_ONE_TO_ONE:
        scaler = MinMaxScaler(feature_range=(-1, 1))
    elif action == NormalizeActionEnum.ZERO_TO_ONE:
        scaler = MinMaxScaler(feature_range=(0, 1))
    else:
        scaler = StandardScaler()
    columns_normalize = df.columns.difference(avoid_columns)
    df[columns_normalize] = scaler.fit_transform(df[columns_normalize])
    file_save = f"normalize_{action.value}_{file_in}"
    save_to_csv(data_frame=df, file_save=file_save)
