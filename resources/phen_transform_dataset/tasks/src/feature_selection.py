"""Select variables by criteria"""
import re

import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
from src.helpers.file_access import get_file_to_data_frame, FolderList, save_to_csv, get_file


def select_column_by_text_like(file_in: str, percentage: float) -> None:
    """Keep only columns that are more or equal to percentage
    Args:
        file_in: File to get the data and is in upload file folder
        percentage: Range to select columns (0 y 1)
    """
    if percentage > 1 or percentage < 0:
        raise ValueError("Percentage only be 0 to 1")
    df = get_file_to_data_frame(file_name=file_in, folder=FolderList.UPLOAD)
    percentage_no_null = df.notnull().mean()
    select_columns = percentage_no_null[percentage_no_null >
                                        percentage].index.values
    print(select_columns)
    df_filter = df[select_columns]
    file_out = f"select_percentage_{file_in}"
    save_to_csv(data_frame=df_filter, file_save=file_out)


def select_column_by_patter_like(file_in: str, patter_like: str) -> None:
    """Keep only columns that have same str of patters
    Args:
        file_in: File to get the data and is in upload file folder
        patter_like: str of patterns
    """
    df = get_file_to_data_frame(file_name=file_in, folder=FolderList.UPLOAD)
    patter = re.compile(patter_like, re.IGNORECASE)
    df_filter = df.filter(regex=patter)
    print(df_filter.columns.values)
    file_out = f"select_patter_{patter_like}_{file_in}"
    save_to_csv(data_frame=df_filter, file_save=file_out)


def select_column_by_list_patter_and(file_in: str, patters_like: list) -> None:
    """Keep only columns that have same list of patters
    Args:
        file_in: File to get the data and is in upload file folder
        patter_like: List of patterns
    """
    df = get_file_to_data_frame(file_name=file_in, folder=FolderList.UPLOAD)
    patter = re.compile(r"*".join(patters_like), re.IGNORECASE)
    df_filter = df.filter(regex=patter)
    print(df_filter.columns.values)
    file_out = f"select_patter_{patters_like}_{file_in}"
    save_to_csv(data_frame=df_filter, file_save=file_out)


def select_column_by_patter_like_with_static(
    file_in: str,
    patter_like: str,
    static_columns: list,
) -> None:
    """Keep only columns that have same str of patters, and some static columns 
    Args:
        file_in: File to get the data and is in upload file folder
        patter_like: str of patterns
        static_columns (list): column that keep on dataset
    """
    df = get_file_to_data_frame(file_name=file_in, folder=FolderList.UPLOAD)
    patter = re.compile(patter_like, re.IGNORECASE)
    df_filter = df.filter(regex=patter)
    join_static_columns = static_columns + df_filter.columns.tolist()
    print(f"Static columns - {join_static_columns}")
    fd_static_filter = df[join_static_columns]
    print(fd_static_filter.columns.values)
    file_out = f"select_patter_{patter_like}_{
        "-".join(world[0] for world in static_columns)
    }_{file_in}"
    save_to_csv(data_frame=fd_static_filter, file_save=file_out)


def select_by_correlation(file_in: str, threshold: float, create_heatmap: bool = False) -> None:
    """Keep only column that are correlated lest that threshold 

    Args:
        file_in (str): file to work
        threshold (float): limit to include the column on the new dataset
    """
    df = get_file_to_data_frame(file_name=file_in, folder=FolderList.UPLOAD)
    print(f"create heatmap - {create_heatmap}")
    if create_heatmap:
        file_only_name = file_in.split(".")
        corr_matrix = df.corr()
        plt.figure(figsize=(80, 60))
        sns.heatmap(corr_matrix, annot=True, cmap='coolwarm')
        plt.title(f'Correlation Matrix {file_only_name[0]}')
        file_name_png = f'{file_only_name[0]}.png'
        file_save = get_file(file_name=file_name_png, folder=FolderList.UPLOAD)
        plt.savefig(file_save)
    corr_matrix = df.corr().abs()
    upper_tri = corr_matrix.where(
        np.triu(np.ones(corr_matrix.shape), k=1).astype(bool))

    to_drop = [column for column in upper_tri.columns if any(
        upper_tri[column] >= threshold)]
    df.drop(to_drop, axis=1, inplace=True)

    file_out = f"correlation_{file_in}"
    save_to_csv(data_frame=df, file_save=file_out)
