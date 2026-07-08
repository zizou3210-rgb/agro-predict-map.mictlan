"""Skelton for class to predict"""
from dataclasses import dataclass
from enum import Enum
from typing import List


class MachineNames(Enum):
    """Enum for machine names"""
    RANDOM_FOREST_REGRESSION = "random_forest_regression"
    EXTREME_GRADIENT_BOOSTING_REGRESSION = "extreme_gradient_boost_regression"
    BAYESIAN_RIDGE_REGRESSION = "bayesian_prediction_regression"
    LASSO_REGRESSION = "lasso_regression"
    SUPPORT_VECTOR_REGRESSION = "support_vector_regression"


class MachinesTypes(Enum):
    """Enum for machine types"""
    REGRESSION = "regression"
    CLASSIFICATION = "clarification"


HyperTypeValueEnum = Enum('HyperTypeValueEnum', [
    ('FLOAT', 'float'),
    ('INT', 'int'),
    ('CATEGORY', 'category'),
])


@dataclass
class LimitHyperParameter():
    """Limit for hyper parameter
    """
    low_value: str = None
    high_value: str = None
    catalogue_values: list[str] = None


@dataclass
class HyperParameterRebuild:
    """Basic hyper parameters for rebuild"""
    name: str
    value: str


def convert_str_to_machine_name(machine_name: str) -> MachineNames:
    """Convert string to machine name

    Args:
        machine_name (str): Machine name

    Returns:
        MachineNames: Machine name
    """
    return MachineNames(machine_name)


@dataclass
class MachineDefaultDefinition:
    """Definition machine from with use default
    """
    machine_name: MachineNames
    rebuild_hyper_parameters: List[HyperParameterRebuild] = None
