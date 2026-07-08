from enum import Enum

class RowValidEnum(Enum):
    PASS = 0
    VALUE_OR_REMOVE = 1



class RowValid:
    def __init__(self, column: str, valid: RowValidEnum ) -> None:
        self.column = column
        self.valid = valid