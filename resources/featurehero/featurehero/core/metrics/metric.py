"""Get metric from machines    """
from typing import Dict

from sklearn.metrics import (
    d2_absolute_error_score,
    d2_pinball_score,
    d2_tweedie_score,
    explained_variance_score,
    max_error,
    mean_absolute_error,
    mean_absolute_percentage_error,
    mean_gamma_deviance,
    mean_poisson_deviance,
    mean_squared_error,
    mean_squared_log_error,
    median_absolute_error,
    r2_score,
    root_mean_squared_error,
    root_mean_squared_log_error,
)
import pandas as pd


from featurehero.core.metrics.metric_enums import MetricEnum
from featurehero.core.key_env import IS_DEBUG


class Metric():
    """Class to get error metrics
    """

    def __init__(
            self,
            y_predicted: pd.Series,
            y_test: pd.Series,
            x_test: pd.Series,
    ) -> None:
        self._y_predicted = y_predicted
        self._y_true = y_test
        self._x_true = x_test
        self._metrics = {}
        self._predict_versus_true = []
        self._y_predicted_no_negative = y_predicted.copy()
        self._y_predicted_no_negative[
            self._y_predicted_no_negative < 0
        ] = 0.0001
        if (self._y_true <= 0).any():
            print(
                "[METRIC WARNING] Found non-positive values in y_true"
                " (real values). "
                "Some metrics might produce invalid results."
            )
        if (self._y_predicted_no_negative <= 0).any():
            print(
                "[METRIC WARNING] Found non-positive values in"
                " y_predicted_no_negative (predicted values). "
                "Some metrics might produce invalid results."
            )

        self.calculate_metric_prediction()

    def calculate_metric_prediction(self) -> None:
        """Calculate all metrics
        """
        self._metrics[
            MetricEnum.D2_ABSOLUTE_ERROR_SCORE.value
        ] = d2_absolute_error_score(
            y_pred=self._y_predicted, y_true=self._y_true)
        self._metrics[MetricEnum.D2_PINBALL_SCORE.value] = d2_pinball_score(
            y_pred=self._y_predicted, y_true=self._y_true)
        self._metrics[MetricEnum.D2_TWEEDIE_SCORE.value] = d2_tweedie_score(
            y_pred=self._y_predicted, y_true=self._y_true)
        self._metrics[
            MetricEnum.EXPLAINED_VARIANCE_SCORE.value
        ] = explained_variance_score(
            y_pred=self._y_predicted, y_true=self._y_true)
        self._metrics[MetricEnum.MAX_ERROR.value] = max_error(
            y_pred=self._y_predicted, y_true=self._y_true)
        self._metrics[
            MetricEnum.MEAN_ABSOLUTE_ERROR.value
        ] = mean_absolute_error(
            y_pred=self._y_predicted, y_true=self._y_true)
        self._metrics[
            MetricEnum.MEAN_ABSOLUTE_PERCENTAGE_ERROR.value
        ] = mean_absolute_percentage_error(
            y_pred=self._y_predicted, y_true=self._y_true
        )
        self._metrics[
            MetricEnum.MEAN_GAMMA_DEVIANCE.value] = mean_gamma_deviance(
            y_pred=self._y_predicted_no_negative,
            y_true=self._y_true,
        )
        self._metrics[
            MetricEnum.MEAN_POISSON_DEVIANCE.value] = mean_poisson_deviance(
            y_pred=self._y_predicted_no_negative,
            y_true=self._y_true,
        )
        self._metrics[
            MetricEnum.MEAN_SQUARED_ERROR.value] = mean_squared_error(
            y_pred=self._y_predicted_no_negative, y_true=self._y_true)
        self._metrics[
            MetricEnum.MEAN_SQUARED_LOG_ERROR.value] = mean_squared_log_error(
            y_pred=self._y_predicted_no_negative, y_true=self._y_true)
        self._metrics[
            MetricEnum.MEDIAN_ABSOLUTE_ERROR.value] = median_absolute_error(
            y_pred=self._y_predicted_no_negative, y_true=self._y_true)
        self._metrics[
            MetricEnum.R2_SCORE.value] = r2_score(
            y_pred=self._y_predicted_no_negative, y_true=self._y_true)
        self._metrics[
            MetricEnum.ROOT_MEAN_SQUARED_ERROR.value
        ] = root_mean_squared_error(
            y_pred=self._y_predicted_no_negative, y_true=self._y_true)
        self._metrics[
            MetricEnum.ROOT_MEAN_SQUARED_LOG_ERROR.value
        ] = root_mean_squared_log_error(
            y_pred=self._y_predicted_no_negative, y_true=self._y_true)
        self._metrics[
            MetricEnum.ACCURACY_MEAN_ABSOLUTE_PERCENTAGE_ERROR.value
        ] = 1 - mean_absolute_percentage_error(
            y_pred=self._y_predicted,
            y_true=self._y_true,
        )

    def get_error_predict_versus_true(
        self,
        pivot: float,
        sort: str = 'error',
    ) -> None:
        """List of error with upper first

        Args:
            pivot (float): Pivot to print
            sort (str, optional): Way to sorter. Defaults to 'error'.

        """
        number_upper = 0
        list_upper = []
        if IS_DEBUG:
            print(f"#### list on error upper -> {pivot}")
        for predicted, true in zip(self._y_predicted, self._y_true):
            error = abs(
                (true - predicted) / true)
            if error > pivot:
                number_upper = number_upper + 1
                list_upper.append(
                    {'truth': true, 'predict': predicted, 'error': error})
        if IS_DEBUG:
            print(
                f"Number of element -> {len(self._y_true)} "
                f"number of upper error -> {number_upper}"
            )
        return sorted(
            list_upper,
            key=lambda x: x[sort],
            reverse=True
        )

    def get_all_metric(self) -> Dict:
        """Get all metrics

        Returns:
            ndarray: List of metrics
        """
        return self._metrics

    def get_single_metric(self, metric: MetricEnum) -> float:
        """Get metric by enum

        Args:
            metric (MetricEnum): Metric to get

        Raises:
            KeyError: Not found the metric

        Returns:
            float: return the metric
        """
        if metric.value in self._metrics:
            return self._metrics[metric.value]
        raise KeyError("Metric is not valid")

    def free_memory(self) -> None:
        """Clean memory
        """
        self._x_true = None
        self._y_true = None
        self._y_predicted = None
        self._y_predicted_no_negative = None
