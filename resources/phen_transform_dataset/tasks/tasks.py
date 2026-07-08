"""Run all task"""
import gc

from celery import Celery
from src.helpers.key_env import REDIS_BROKEN, IS_DEBUG, FolderList, FileInformation
from src.feature_selection import (
    select_by_correlation,
    select_column_by_list_patter_and,
    select_column_by_patter_like_with_static,
    select_column_by_patter_like,
    select_column_by_text_like,
)
from src.missing_empty import missing_by_mean_for_features
from src.normalize.action_enums import convert_str_into_normalize_action
from src.normalize.process import normalize_dataset
from src.search_data.weather_power_nasa.enum_weather import (
    convert_string_to_transform_weather_action,
    convert_string_to_column_definition,
    convert_string_to_feature_power_list,
)
from src.search_data.weather_power_nasa.search_power_api import WeatherExportDataFrame

if IS_DEBUG:
    print(REDIS_BROKEN)

app = Celery(
    'phen_transform',
    broker=REDIS_BROKEN,
    queue='transform',
)


@app.task(name="feature_selection-keep_percentage_of_no_empty")
def keep_percentage_of_no_empty(file_csv: str, percentage_of_no_empty: float) -> None:
    """Read csv and only pass the column that have more or equal to percentage the cell with values

    Args:
        file_csv (str): name of file 
        percentage_of_no_empty (float): percentage valid

    Returns:
        _type_: None
    """
    print(
        f"Parameters: file - {file_csv} percentage - {percentage_of_no_empty}")
    select_column_by_text_like(
        file_in=file_csv, percentage=float(percentage_of_no_empty))
    gc.collect()
    return "success"


@app.task(name="feature_selection-keep_patter_like")
def keep_patter_like(file_csv: str, patter_like: str) -> None:
    """Read csv and only pass the column that have like column name

    Args:
        file_csv (str): name of file 
        patter_like (str): patter to like it

    Returns:
        _type_: None
    """
    print(f"Parameters: file - {file_csv} percentage - {patter_like}")
    select_column_by_patter_like(file_in=file_csv, patter_like=patter_like)
    gc.collect()
    return "success"

# TODO: To verification


@app.task(name="feature_selection-keep_patter_list_like")
def keep_patter_list_like(file_csv: str, patters_like: str) -> None:
    """Read csv and only pass the column that have like column in a list split by @

    Args:
        file_csv (str): name of file 
        patter_like (str): patter to like to convert it a list with @ like common

    Returns:
        _type_: None
    """
    print(f"Parameters: file - {file_csv} percentage - {patters_like}")
    select_column_by_list_patter_and(
        file_in=file_csv, patters_like=patters_like.split("$"))
    gc.collect()
    return "success"


@app.task(name="feature_selection-patter_like_with_static")
def patter_like_with_static(file_csv: str, patter_like: str, static_columns: str) -> None:
    """Read csv and only pass the column that have like column name

    Args:
        file_csv (str): name of file 
        patter_like (str): patter to like it
        static_columns (str): name of column in str split by , 'coma' 

    Returns:
        _type_: None
    """

    print(f"Parameters: file - {file_csv} percentage - {patter_like}")
    select_column_by_patter_like_with_static(
        file_in=file_csv,
        patter_like=patter_like,
        static_columns=static_columns.split(",")
    )
    gc.collect()
    return "success"


@app.task(name="feature_selection-correlation")
def feature_selection_correlation(file_csv: str, threshold: str, create_heatmap: str) -> None:
    """Read csv and only pass the column that have less correlation threshold

    Args:
        file_csv (str): file to get from upload folder
        threshold (str): limit of correlation
        create_png (str): if can create some png image (heatmap)

    Returns:
        _type_: _description_
    """

    print(f"Parameters :] file - {file_csv} threshold - {
          threshold} - create_png - {create_heatmap}")
    select_by_correlation(
        file_in=file_csv,
        threshold=float(threshold),
        create_heatmap=bool(create_heatmap),
    )
    gc.collect()
    return "success"


@app.task(name="missing_fill_average")
def task_missing_fill_average(file_csv: str) -> None:
    """Read csv and fill all NAN or empty to avg

    Args:
        file_csv (str): file to fill
    Returns:
        _type_: _description_
    """
    if IS_DEBUG:
        print(f"Parameters :] file - {file_csv}")
    missing_by_mean_for_features(
        file_in=file_csv,
        folder_file=FolderList.UPLOAD,
    )
    gc.collect()
    return "success"


@app.task(name="normalize_dataset")
def task_normalize_dataset(file_csv: str, action_str: str, avoid_columns_str: str) -> None:
    """Normalize all dataset

    Args:
        file_in (str): file to normalize
        action (str): str the list of action to normalize ()
    """
    print(f"Parameters :] file - {file_csv} action - {
          action_str} avoid columns - {avoid_columns_str}")
    avoid_columns = avoid_columns_str.split(",")
    action = convert_str_into_normalize_action(action_str=action_str)
    normalize_dataset(file_in=file_csv,
                      folder_file=FolderList.UPLOAD, action=action, avoid_columns=avoid_columns)


@app.task(name="search_data_power_hourly")
def task_search_data_power_hourly(
    file_csv: str,
    columns_json_str: str,
    feature_file: str,
) -> None:
    """Get data every day from NASA power

    Args:
        file_csv (str): file with variables 
        columns_json_str (str): column to get date start and end and get lat and lon
        feature_file (str): features to extract and metrics
    """
    print(f"Parameters :] file - {
        file_csv
    } columns  - {
        columns_json_str
    } feature file - {
        feature_file
    } ")
    columns_definition = convert_string_to_column_definition(
        column_definition_str=columns_json_str
    )
    file_information = FileInformation(_file_name=file_csv)
    print(f"columns definition {columns_definition}")
    weather = WeatherExportDataFrame(
        file_information=file_information,
        columns_definition=columns_definition,
        feature_file=feature_file,
    )
    weather.fetching_wheat_daily()
    weather.save()
    del weather
    gc.collect()


@app.task(name="search_data_power_monthly")
def task_search_data_power_monthly(
    file_csv: str,
    columns_json_str: str,
    feature_file: str,
) -> None:
    """Get data every month from NASA power

    Args:
        file_csv (str): file with variables 
        columns_json_str (str): column to get date start and end and get lat and lon
        feature_file (str): features to extract and metrics
    """
    print(f"Parameters :] file - {
        file_csv
    } columns  - {
        columns_json_str
    } features file - {
        feature_file
    } ")
    columns_definition = convert_string_to_column_definition(
        column_definition_str=columns_json_str
    )
    file_information = FileInformation(_file_name=file_csv)
    print(f"columns definition {columns_definition}")
    weather = WeatherExportDataFrame(
        file_information=file_information,
        columns_definition=columns_definition,
        feature_file=feature_file
    )
    weather.fetching_wheat_monthly()
    weather.save()
    del weather
    gc.collect()
