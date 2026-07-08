"""Get all data class and enum for weather"""
import os
import json
from dataclasses import dataclass
from enum import Enum


from dotenv import load_dotenv


load_dotenv()


class FormatPowerApiEnum(Enum):
    """Type of format for power API

    Args:
        Enum (_type_): _description_
    """
    JSON = "json"


class CommunityPowerApiEnum(Enum):
    """Type of community for power API

    Args:
        Enum (_type_): _description_
    """
    RE = "re"


# class FeaturesPowerApiEnum(Enum):
#     """Enum to get from server

#     Args:
#         Enum (_type_): _description_
#     """
#     ALLSKY_SFC_SW_DWN = "ALLSKY_SFC_SW_DWN"
#     CLRSKY_SFC_SW_DWN = "CLRSKY_SFC_SW_DWN"
#     ALLSKY_KT = "ALLSKY_KT"
#     ALLSKY_SFC_LW_DWN = "ALLSKY_SFC_LW_DWN"
#     ALLSKY_SFC_PAR_TOT = "ALLSKY_SFC_PAR_TOT"
#     CLRSKY_SFC_PAR_TOT = "CLRSKY_SFC_PAR_TOT"
#     ALLSKY_SFC_UVA = "ALLSKY_SFC_UVA"
#     ALLSKY_SFC_UVB = "ALLSKY_SFC_UVB"
#     ALLSKY_SFC_UV_INDEX = "ALLSKY_SFC_UV_INDEX"
#     T2M = "T2M"
#     T2MDEW = "T2MDEW"
#     T2MWET = "T2MWET"
#     TS = "TS"
#     T2M_RANGE = "T2M_RANGE"
#     T2M_MAX = "T2M_MAX"
#     T2M_MIN = "T2M_MIN"
#     QV2M = "QV2M"
#     RH2M = "RH2M"
#     PRECTOTCORR = "PRECTOTCORR"
#     PS = "PS"
#     WS10M = "WS10M"
#     WS10M_MAX = "WS10M_MAX"
#     WS10M_MIN = "WS10M_MIN"
#     WS10M_RANGE = "WS10M_RANGE"
#     WD10M = "WD10M"
#     WS50M = "WS50M"
#     WS50M_MAX = "WS50M_MAX"
#     WS50M_MIN = "WS50M_MIN"
#     WS50M_RANGE = "WS50M_RANGE"
#     WD50M = "WD50M"


@dataclass
class ColumnsDefinition():
    """All column to get information from power API
    """
    latitude_column: str
    longitude_column: str
    start_date_column: str
    end_date_column: str


@dataclass
class UrlPowerAPI():
    """List of endpoint to get data from nasa power API
    """
    hourly_url: str = os.getenv(
        'HOURLY_URL', "https://power.larc.nasa.gov/api/temporal/hourly/point")
    daily_url: str = os.getenv(
        'DAILY_URL', "https://power.larc.nasa.gov/api/temporal/dayly/point")
    monthly_url: str = os.getenv(
        'MONTHLY_URL', "https://power.larc.nasa.gov/api/temporal/monthly/point")


def url_power_enum_to_text(server: str):
    """get text of 

    Args:
        server (ServerPowerEnum): _description_

    Raises:
        NotImplementedError: _description_

    Returns:
        _type_: _description_
    """
    url = UrlPowerAPI()
    if server == url.hourly_url:
        return "hourly"
    if server == url.daily_url:
        return "daily"
    if server == url.monthly_url:
        return "mouthy"
    raise NotImplementedError("Not valid server power enum")


class TransformWeatherActionEnum(Enum):
    """Action to transform weather"""
    MEAN = "mean"
    MAX = "max"
    MINUS = "minus"
    RANGE = "range"


def convert_string_to_transform_weather_action(action_str) -> TransformWeatherActionEnum:
    """Cast str into action

    Returns:
        TransformWeatherActionEnum: action to work with it on API
    """
    if action_str.lower() == TransformWeatherActionEnum.MAX.value.lower():
        return TransformWeatherActionEnum.MAX
    if action_str.lower() == TransformWeatherActionEnum.MINUS.value.lower():
        return TransformWeatherActionEnum.MINUS
    if action_str.lower() == TransformWeatherActionEnum.MEAN.value.lower():
        return TransformWeatherActionEnum.MEAN
    if action_str.lower() == TransformWeatherActionEnum.RANGE.value.lower():
        return TransformWeatherActionEnum.RANGE
    raise ModuleNotFoundError("Convert not valid - for normalize action")


def convert_string_to_column_definition(column_definition_str) -> ColumnsDefinition:
    """Convert string into columns definition

    Args:
        action_str (_type_): string to cast

    Returns:
        ColumnDefinition: object column definition
    """
    column_definition_json = json.loads(column_definition_str)
    if "latitude_column" not in column_definition_json:
        raise NameError("latitude_column don't exist")
    if "longitude_column" not in column_definition_json:
        raise NameError("longitude_column don't exist")
    if "start_date_column" not in column_definition_json:
        raise NameError("start_date_column don't exist")
    if "end_date_column" not in column_definition_json:
        raise NameError("end_date_column don't exist")
    column_definition = ColumnsDefinition(
        latitude_column=column_definition_json["latitude_column"],
        longitude_column=column_definition_json["longitude_column"],
        end_date_column=column_definition_json["end_date_column"],
        start_date_column=column_definition_json["start_date_column"],
    )
    return column_definition
