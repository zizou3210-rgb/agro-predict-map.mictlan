"""Create some machine
    """

from featurehero.core.metrics.metric_enums import MetricEnum
from featurehero.services.machines.machine_enums import MachineNames
from featurehero.services.machines.machine import (
    BayesianRidgeRegression,
    ExtremeGradientBoostRegression,
    LassoRegression,
    MachineRegression,
    RandomForestRegression,
    SupportVectorRegression,
)


def machine_build_regression_optimization_decimal(
        machine_name: MachineNames,
        deep_decimal: int,
        metric_selection: MetricEnum = None,
) -> MachineRegression:
    """Build some machine for optimization with random values

    Args:
        machine_definition (MachineJson): Machine definition
        deep_decimal (int): Number of decimal to mutate

    Returns:
        MachineJson: Return child of Machine Json to run it
    """
    machine = build_machine_regression(
        machine_name=machine_name,
        metric_selection=metric_selection,
    )
    machine.force_mutate_hyper_parameters(deep_decimal=deep_decimal)
    return machine


def build_machine_regression(
        machine_name: MachineNames,
        metric_selection: MetricEnum = None,
) -> MachineRegression:
    """Build some machine for optimization

    Args:
        machine_definition (MachineJson): Machine definition

    Raises:
        NotImplementedError: The machine don't exist

    Returns:
        MachineJson: Return child of Machine Json to run it
    """
    machine = None
    if machine_name == MachineNames.RANDOM_FOREST_REGRESSION:
        machine = RandomForestRegression(metric_selection=metric_selection)
    if machine_name == MachineNames.EXTREME_GRADIENT_BOOSTING_REGRESSION:
        machine = ExtremeGradientBoostRegression(
            metric_selection=metric_selection
        )
    if machine_name == MachineNames.BAYESIAN_RIDGE_REGRESSION:
        machine = BayesianRidgeRegression()
    if machine_name == MachineNames.LASSO_REGRESSION:
        machine = LassoRegression()
    if machine_name == MachineNames.SUPPORT_VECTOR_REGRESSION:
        machine = SupportVectorRegression()
    if machine is None:
        raise NotImplementedError("Don't exist machine to run it")
    return machine
