import pandas as pd
import numpy as np
from search_data.csv.enum import GroupByDateEnum, OperationToGroupEnum
import datetime

class WeatherSourceCSV():
    def __init__(self, file_path: str, column_date: str) -> None:
        self.file_path = file_path
        self.df = pd.read_csv(file_path, parse_dates=[column_date])
        self.column_key = column_date
        self.df_extracted = None
        self.format_date = '%Y-%m-%d'
        self.data = []

    def clean_data(self):
        self.df_extracted = None
        self.data = []

    def extract_date(
            self,
            start: str,
            end: str,
    ) -> pd.DataFrame:
        self.df_extracted = self.df[
            (self.df[self.column_key] >= start) &
            (self.df[self.column_key] <= end)
        ]

    def save_extract(self, file_path: str):
        self.df_extracted.to_csv(file_path, index=False)
    
    def save_transform(self, file_path: str):
        df = pd.DataFrame.from_dict(self.data)
        df.to_csv(file_path, index=False)

    def transform_date(
            self,
            start: str,
            end: str,  
            group_by: GroupByDateEnum,
            operation_group: OperationToGroupEnum,
            is_clean_data: bool = True,
            is_debug: bool = False,
        ):
        if is_clean_data:
            self.clean_data()
        self.extract_date(start=start, end=end)
        dict_one_row = {}
        start_date = datetime.datetime.strptime(start, self.format_date)
        end_date = datetime.datetime.strptime(end, self.format_date) 
        res_date = start_date
        day_to_group = 1
        if group_by == GroupByDateEnum.THIRTY_DAY:
            day_to_group = 30
        elif group_by == GroupByDateEnum.SEVEN_DAY:
            day_to_group = 7
        elif group_by == GroupByDateEnum.FIFTEEN_DAY:
            day_to_group = 15
        else: 
            day_to_group = 1
        while res_date <= end_date:
            res_date_end = res_date + datetime.timedelta(days=day_to_group) - datetime.timedelta(seconds=1)
            if res_date_end >  end_date:
                print("Upper date")
                res_date_end = end_date
            if is_debug:
                print(res_date,' - ', res_date_end,'- end ', end_date)
            df_operate = self.df_extracted[ 
                (self.df_extracted[self.column_key] >= res_date) &
                (self.df_extracted[self.column_key] <= res_date_end)
            ]
            for column in self.df_extracted:
                if column != self.column_key:
                    column_name = "{}-{}_{}".format(res_date.strftime("%Y%m%d"), res_date_end.strftime("%Y%m%d"),column)
                    if is_debug:
                        print(column_name)
                    if operation_group == OperationToGroupEnum.AVG:
                        column_name_operation = "{}_AVG".format(column_name)
                        dict_one_row[column_name_operation] = np.nanmean(df_operate[column])
            res_date += datetime.timedelta(days=day_to_group)
        self.data.append(dict_one_row)
           

