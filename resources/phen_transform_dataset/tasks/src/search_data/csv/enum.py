from enum import Enum


class GroupByDateEnum(Enum):
    DAY = 1
    SEVEN_DAY = 2
    FIFTEEN_DAY = 3
    THIRTY_DAY = 4


class OperationToGroupEnum(Enum):
    AVG = 0
