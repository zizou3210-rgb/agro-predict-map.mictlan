"""To run test from files"""

import sys

from celery.app import Celery
from src.helpers.key_env import REDIS_BROKEN
from src.normalize.action_enums import convert_str_into_normalize_action
from src.search_data.weather_power_nasa.search_power_api import (
    WeatherExportDataFrame,
)
from src.search_data.weather_power_nasa.enum_weather import (
    convert_string_to_column_definition,
)
from src.helpers.file_access import FileInformation
from src.helpers.file_access import FolderList
from src.normalize.process import normalize_dataset
from src.missing_empty import missing_by_mean_for_features

if __name__ == "__main__":
    if len(sys.argv) > 1:
        print(f"Run with props action - {sys.argv[1]}")
        app = Celery(
            "phen_transform",
            broker_url=REDIS_BROKEN,
            queue="transform",
        )
        action = sys.argv[1]
        if action == "keep_percentage_of_no_empty":
            print("Run - keep_percentage_of_no_empty")
            print(f"file -> {sys.argv[2]}, percentage -> {sys.argv[3]}")
            app.send_task(
                name="feature_selection-keep_percentage_of_no_empty",
                args=(
                    sys.argv[2],
                    sys.argv[3],
                ),
            )
        elif action == "keep_patter_like":
            print("Run - keep_patter_like")
            print(f"file - {sys.argv[2]}, percentage - {sys.argv[3]}")
            app.send_task(
                name="feature_selection-keep_patter_like",
                args=(
                    sys.argv[2],
                    sys.argv[3],
                ),
            )
        elif action == "keep_patter_list_like":
            print("Run - keep_patter_list_like")
            print(f"file -> {sys.argv[2]}, percentage -> {sys.argv[3]}")
            app.send_task(
                name="feature_selection-keep_patter_list_like",
                args=(
                    sys.argv[2],
                    sys.argv[3],
                ),
            )
        elif action == "patter_like_with_static":
            print("Run - patter_like_with_static")
            print(
                f"file -> {sys.argv[2]}, patter -> {sys.argv[3]}, columns -> {sys.argv[4]}"
            )
            app.send_task(
                name="feature_selection-patter_like_with_static",
                args=(
                    sys.argv[2],
                    sys.argv[3],
                    sys.argv[4],
                ),
            )
        elif action == "feature_selection-correlation":
            print("Run - feature_selection-correlation")
            information_print = f"file -> {sys.argv[2]}, threshold -> {sys.argv[3]}"
            information_print = information_print + \
                f", create_heatmap -> {sys.argv[4]}"
            print(information_print)
            app.send_task(
                name="feature_selection-correlation",
                args=(
                    sys.argv[2],
                    sys.argv[3],
                    sys.argv[4],
                ),
            )
        elif action == "missing_fill_average":
            print("Run - missing_fill_average")
            print(f"file -> {sys.argv[2]}")
            app.send_task(name=action, args=(sys.argv[2],))

        elif action == "normalize_dataset":
            print("Run - normalize_dataset")
            print(
                f"file -> {sys.argv[2]} action -> {sys.argv[3]} avoid columns - {sys.argv[4]}"
            )
            app.send_task(
                routing_key="high_priority",
                name="normalize_dataset",
                args=(
                    sys.argv[2],
                    sys.argv[3],
                    sys.argv[4],
                ),
            )
        elif action == "search_data_power_hourly":
            print("Run - search_data_power_hourly")
            information_print = f"file -> {sys.argv[2]} action -> {sys.argv[3]}"
            information_print = (
                information_print
                + f" columns - {sys.argv[4]} features -> {sys.argv[5]}"
            )
            print(information_print)
            app.send_task(
                name="search_data_power_hourly",
                args=(
                    sys.argv[2],
                    sys.argv[3],
                    sys.argv[4],
                    sys.argv[5],
                ),
            )
        elif action == "search_data_power_monthly":
            print("Run - search_data_power_monthly")
            information_print = f"file -> {sys.argv[2]} action -> {sys.argv[3]}"
            information_print = (
                information_print
                + f" columns - {sys.argv[4]} features -> {sys.argv[5]}"
            )
            print(information_print)
            app.send_task(
                name="search_data_power_monthly",
                args=(
                    sys.argv[2],
                    sys.argv[3],
                    sys.argv[4],
                    sys.argv[5],
                ),
            )
        else:
            print("Not action valid")

    else:
        print("Only test")
        # Fill missing data
        # missing_by_mean_for_features(
        #     file_in="2.0.LRACE_fenotipico.csv",
        #     folder_file=FolderList.UPLOAD,
        # )

        normalize_dataset(
            file_in="2.1.LRACE_fenotipico_fill.csv",
            folder_file=FolderList.UPLOAD,
            action=convert_str_into_normalize_action(action_str="standard_scale"),
            avoid_columns="Yield".split(","),
        )

        # weather = WeatherExportDataFrame(
        #     file_information=FileInformation(
        #         _file_name="1.2.LRACE_ready_to_get_climatic.csv"),
        #     columns_definition=convert_string_to_column_definition(
        #         column_definition_str='{"latitude_column": "latitud", "longitude_column": 	"longitude",	"start_date_column": "StartDate", "end_date_column" : "EndDate"}'
        #     ),
        #     feature_file="1.2.LRACE_ready_to_get_climatic.json",
        # )
        # weather.fetching_wheat_monthly()
        # weather.save()

    print("end")
