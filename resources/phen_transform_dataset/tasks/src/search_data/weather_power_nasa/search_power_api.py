"""Search data from power server"""

from calendar import monthrange
from dataclasses import dataclass, field
from datetime import datetime
import time
import json
from typing import List

import pandas as pd
import requests_cache
import numpy as np


from src.search_data.weather_power_nasa.enum_weather import (
    ColumnsDefinition,
    CommunityPowerApiEnum,
    convert_string_to_transform_weather_action,
    FormatPowerApiEnum,
    TransformWeatherActionEnum,
    UrlPowerAPI,
)
from src.helpers.file_access import StorageFile
from src.helpers.key_env import FileInformation, FolderList


@dataclass
class FeatureDefinition:
    """Convert a definition json in a class"""

    feature_name: str = ""
    translate: str = ""
    metrics: List[TransformWeatherActionEnum] = field(default_factory=list)


@dataclass
class APiClient:
    """Client on session"""

    url: str
    session: requests_cache.CachedSession


class WeatherExportDataFrame:
    """Search on nasa power and get data"""

    def __init__(
        self,
        file_information: FileInformation,
        columns_definition: ColumnsDefinition,
        feature_file: str,
    ) -> None:
        self._storage = StorageFile(file_information=file_information)
        self._columns_definition = columns_definition
        self._feature_file = feature_file
        self._df = self._storage.get_csv_to_data_frame()
        self._initial_value_for_row_climatic = -100.0
        self._features: list[FeatureDefinition] = []
        self._read_feature()
        self._api = APiClient(
            url=UrlPowerAPI().hourly_url,
            session=requests_cache.CachedSession(
                self._storage.get_file_on_files_repository(
                    folder=FolderList.TEMP, file_name="wheat_cache_sqlite"
                )
            ),
        )

    def _read_feature(self) -> None:
        path_feature_file = self._storage.get_file_on_files_repository(
            file_name=self._feature_file
        )
        with open(path_feature_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        for dictionary in data:
            if "feature" not in dictionary:
                raise FileNotFoundError(
                    f"File don't have a feature valid on {self._feature_file}"
                )
            translate = dictionary["feature"]
            if "translate" in dictionary and dictionary["translate"] != "":
                translate = dictionary["translate"]
            if "metric" not in dictionary:
                raise FileNotFoundError(
                    f"File don't have a metric valid on {self._feature_file}"
                )
            metrics = []
            metric_array = dictionary["metric"].split(",")
            if len(metric_array) == 0:
                error_message = f"File don't have any metric on {self._feature_file}"
                feature_name = dictionary["feature"]
                error_message = f"{error_message} and feature {feature_name}"
                raise FileNotFoundError(error_message)
            for metric in metric_array:
                metrics.append(convert_string_to_transform_weather_action(metric))
            self._features.append(
                FeatureDefinition(
                    translate=translate,
                    feature_name=dictionary["feature"],
                    metrics=metrics,
                )
            )

    def fetching_wheat_daily(self):
        """Get data from API"""
        self._prepare_data_frame(is_monthly=False)
        for feature in self._features:
            feature_name = feature.feature_name
            for index, row in self._df.iterrows():
                df_weather = self._send_request(row=row, feature_name=feature_name)
                if not df_weather.empty:
                    self._get_features_daily(
                        index=index,
                        df_weather=df_weather,
                        feature=feature,
                    )
                    print(
                        f"Success feature -> {feature_name} of {index} - {self._df.shape[0]}"
                    )
            self.save()

    def _send_request(
        self, row: pd.Series, feature_name: str, is_monthly: bool = False
    ) -> pd.DataFrame:
        """Send request to NASA power

        Returns:
            pd.DataFrame: _description_
        """
        row_start = "date_start"
        row_end = "date_end"
        if is_monthly:
            row_start = "date_start_month"
            row_end = "date_end_month"
        params = {
            "start": row[row_start],
            "end": row[row_end],
            "latitude": row[self._columns_definition.latitude_column],
            "longitude": row[self._columns_definition.longitude_column],
            "community": CommunityPowerApiEnum.RE.value,
            "parameters": feature_name,
            "format": FormatPowerApiEnum.JSON.value,
            "user": "cloud",
            "header": True,
            "time-standard": "lst",
        }
        response = self._api.session.get(
            url=self._api.url,
            params=params,
            headers={"accept": "application/json"},
        )
        if response.status_code == 200:
            df_weather = self._populate_data_frame_weather(
                result=response.json()["properties"]["parameter"][feature_name],
                start_date=pd.to_datetime(row["date_start_month"]),
                end_date=pd.to_datetime(row["date_end_month"]),
            )
            return df_weather
        print(f"Error on {self._api.url}, feature {feature_name} -> {response}")
        if not response.from_cache:
            print("Sleep to prevent error on Server... =(^-^)=")
            time.sleep(5)
        return pd.DataFrame()

    def _prepare_data_frame(self, is_monthly: bool = False):
        """Prepare the data frame cast to date and create new columns like month

        Args:
            last_and_first_day (bool, optional): _description_. Defaults to False.
        """
        self._df["date_start"] = pd.to_datetime(
            self._df[self._columns_definition.start_date_column]
        ).dt.strftime("%Y%m%d")
        self._df["date_end"] = pd.to_datetime(
            self._df[self._columns_definition.end_date_column]
        ).dt.strftime("%Y%m%d")
        print("Data")
        print(self._df[["date_start", "date_end"]].head().to_string())
        if is_monthly:
            self._df["date_start_month"] = (
                self._df["date_start"]
                .apply(self._first_day_of_date)
                .dt.strftime("%Y%m%d")
            )
            self._df["date_end_month"] = (
                self._df["date_end"].apply(self._last_day_of_date).dt.strftime("%Y%m%d")
            )

    def fetching_wheat_monthly(self):
        """Get data from API"""
        self._prepare_data_frame(is_monthly=True)
        for feature in self._features:
            feature_name = feature.feature_name
            self._df[feature_name] = self._initial_value_for_row_climatic
            for index, row in self._df.iterrows():
                df_weather = self._send_request(
                    row=row,
                    feature_name=feature_name,
                    is_monthly=True,
                )
                if not df_weather.empty:
                    self._get_features_monthly(
                        index=index,
                        df_weather=df_weather,
                        feature=feature,
                    )
                    print(
                        f"Success feature -> {
                        feature_name} of {index} - {self._df.shape[0]}"
                    )
            self.save()

    def _populate_data_frame_weather(
        self, result: dict, start_date, end_date
    ) -> pd.DataFrame:
        """Populate data frame with weather data from server

        Args:
            result (dict): result of server
            start_date (_type_): date start
            end_date (_type_): date end

        Returns:
            pd.DataFrame: return data frame with weather data
        """
        columns_date = [
            date.strftime("%Y%m%d")
            for date in pd.date_range(
                start=start_date,
                end=end_date,
            )
        ]
        df_weather = pd.DataFrame(
            index=range(24),
            columns=columns_date,
        )
        for key in result:
            time_index = int(key[-2:])
            day_column = key[:8]
            df_weather.loc[time_index, day_column] = result[key]
        return df_weather

    def _get_features_monthly(
        self,
        index: int,
        df_weather: pd.DataFrame,
        feature: FeatureDefinition,
    ) -> None:
        """Get features from weather on dataframe weather

        Args:
            index (int): point of row
            df_weather (pd.DataFrame): data of weather
            feature (str): feature weather to search
        """
        year_months = self._get_list_year_month(date_list=df_weather.columns.to_list())
        for year_month in year_months:
            columns_month_year = self._get_column_like_month_year(
                year_month=year_month,
                columns=df_weather.columns.to_list(),
            )
            flatten_values = df_weather[columns_month_year].values.flatten()
            if TransformWeatherActionEnum.MEAN in feature.metrics:
                self._add_new_feature_cell_df(
                    column_name=f"{feature.translate}_{
                        TransformWeatherActionEnum.MEAN.value
                    }_{year_month}",
                    index=index,
                    value=np.mean(flatten_values),
                )
            if TransformWeatherActionEnum.MINUS in feature.metrics:
                self._add_new_feature_cell_df(
                    column_name=f"{feature.translate}_{
                        TransformWeatherActionEnum.MINUS.value
                    }_{year_month}",
                    index=index,
                    value=np.min(flatten_values),
                )
            if TransformWeatherActionEnum.MAX in feature.metrics:
                self._add_new_feature_cell_df(
                    column_name=f"{feature.translate}_{
                        TransformWeatherActionEnum.MAX.value
                    }_{year_month}",
                    index=index,
                    value=np.max(flatten_values),
                )
            if TransformWeatherActionEnum.RANGE in feature.metrics:
                self._add_new_feature_cell_df(
                    column_name=f"{feature.translate}_{
                        TransformWeatherActionEnum.RANGE.value
                    }_{year_month}",
                    index=index,
                    value=np.max(flatten_values) - np.min(flatten_values),
                )

    def _get_column_like_month_year(self, columns: list, year_month: str) -> list:
        """Get column like month year"""
        return [column for column in columns if f"{year_month}" in column]

    def _get_list_year_month(self, date_list: list) -> list:
        """Get list of year and month

        Args:
            dates (dict): Start and end date

        Returns:
            list: Return a list of year month
        """
        month_year_unique = set()
        for date_work in date_list:
            month_year_unique.add(date_work[:6])
        return sorted(list(month_year_unique))

    def _get_features_daily(
        self, index: int, df_weather: pd.DataFrame, feature: FeatureDefinition
    ) -> None:
        """Get features from weather on dataframe weather

        Args:
            index (int): point of row
            df_weather (pd.DataFrame): data of weather
            feature (FeatureDefinition): feature definition
        """
        if TransformWeatherActionEnum.MEAN in feature.metrics:
            for column in df_weather.columns:
                self._add_new_feature_cell_df(
                    column_name=f"{feature.translate}_{
                        TransformWeatherActionEnum.MEAN.value}_{column}",
                    index=index,
                    value=df_weather[column].mean(),
                )
        if TransformWeatherActionEnum.MINUS in feature.metrics:
            for column in df_weather.columns:
                self._add_new_feature_cell_df(
                    index=index,
                    column_name=f"{feature.translate}_{
                        TransformWeatherActionEnum.MINUS.value}_{column}",
                    value=df_weather[column].min(),
                )
        if TransformWeatherActionEnum.MAX in feature.metrics:
            for column in df_weather.columns:
                self._add_new_feature_cell_df(
                    column_name=f"{feature.metrics}_{
                        TransformWeatherActionEnum.MAX.value}_{column}",
                    index=index,
                    value=df_weather[column].max(),
                )
        if TransformWeatherActionEnum.RANGE in feature.metrics:
            for column in df_weather.columns:
                self._add_new_feature_cell_df(
                    column_name=f"{feature.translate}_{
                        TransformWeatherActionEnum.RANGE.value}_{column}",
                    index=index,
                    value=df_weather[column].max() - df_weather[column].min(),
                )

    def _add_new_feature_cell_df(self, index: int, column_name: str, value: float):
        """Add new feature on dataframe in a cell

        Args:
            index (int): index of row
            column_name (str): name of column
            value (float): value of metric
        """
        if column_name not in self._df.columns:
            self._df[column_name] = self._initial_value_for_row_climatic
        self._df.at[
            index,
            column_name,
        ] = value

    def save(self):
        """Save file

        Args:
            save_file (_type_): _description_
        """
        columns_to_remove_by_initial_values = []

        for column in self._df.columns:
            if (self._df[column] == self._initial_value_for_row_climatic).all():
                columns_to_remove_by_initial_values.append(column)

        df_with_initial_columns = self._df.drop(
            columns=columns_to_remove_by_initial_values
        )
        self._storage.save_data_frame_to_csv(
            data_frame=df_with_initial_columns,
            prefix="weather",
        )

    def _last_day_of_date(
        self,
        date_to_cast,
    ):
        """Get one date and return a last day of month

        Args:
            date_to_cast (_type_): Date to cast

        Returns:
            _type_: New date with last day of month
        """
        year = int(date_to_cast[:4])
        month = int(date_to_cast[4:6])
        return datetime(
            year=year,
            month=month,
            day=monthrange(year=year, month=month)[1],
        )

    def _first_day_of_date(
        self,
        date_to_cast,
    ):
        """Get one date and return a last day of month

        Args:
            date_to_cast (_type_): Date to cast

        Returns:
            _type_: New date with last day of month
        """
        year = int(date_to_cast[:4])
        month = int(date_to_cast[4:6])
        return datetime(
            year=year,
            month=month,
            day=1,
        )
