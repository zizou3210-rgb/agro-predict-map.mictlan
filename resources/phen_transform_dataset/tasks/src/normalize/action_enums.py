"""All class data and enum for normalize """
from enum import Enum


class NormalizeActionEnum(Enum):
    """Action to normalize"""
    MINUS_ONE_TO_ONE = "minus_one_to_one"
    ZERO_TO_ONE = "zero_to_one"
    DEFAULT = "standard_scale"


def convert_str_into_normalize_action(
        action_str: str, force_default: bool = False
) -> NormalizeActionEnum:
    """Convert text into normalize action

    Args:
        action_str (str): text to convert

    Returns:
        NormalizeActionEnum: action
    """
    if action_str == NormalizeActionEnum.MINUS_ONE_TO_ONE.value:
        return NormalizeActionEnum.MINUS_ONE_TO_ONE
    if action_str == NormalizeActionEnum.ZERO_TO_ONE.value:
        return NormalizeActionEnum.ZERO_TO_ONE
    if action_str == NormalizeActionEnum.DEFAULT.value:
        return NormalizeActionEnum.DEFAULT
    if force_default:
        return NormalizeActionEnum.DEFAULT
    raise ModuleNotFoundError("Convert not valid - for normalize action")
