"""Get metrics from data"""
from enum import Enum
from dataclasses import dataclass


class MetricEnum(Enum):
    """Definition for all metrics

    Args:
        Enum (_type_): _description_
    """
    ACCURACY_MEAN_ABSOLUTE_PERCENTAGE_ERROR = "accuracy_mape"
    D2_ABSOLUTE_ERROR_SCORE = "d2_absolute_error_score"
    D2_PINBALL_SCORE = "d2_pinball_score"
    D2_TWEEDIE_SCORE = "d2_tweedie_score"
    EXPLAINED_VARIANCE_SCORE = "explained_variance_score"
    MAX_ERROR = "max_error"
    MEAN_ABSOLUTE_ERROR = "mean_absolute_error"
    MEAN_ABSOLUTE_PERCENTAGE_ERROR = "mean_absolute_percentage_error"
    MEAN_GAMMA_DEVIANCE = "mean_gamma_deviance"
    MEAN_POISSON_DEVIANCE = "mean_poisson_deviance"
    MEAN_SQUARED_ERROR = "mean_squared_error"
    MEAN_SQUARED_LOG_ERROR = "mean_squared_log_error"
    MEDIAN_ABSOLUTE_ERROR = "median_absolute_error"
    R2_SCORE = "r2_score"
    ROOT_MEAN_SQUARED_ERROR = "root_mean_squared_error"
    ROOT_MEAN_SQUARED_LOG_ERROR = "root_mean_squared_log_error"


@dataclass
class PlotLegends():
    """Basic class for plots
    """
    first_plot_label = "First element"
    second_plot_label = "Second element"
    y_label = "Label Y"
    x_label = "Label X"
    title = "Plot"
