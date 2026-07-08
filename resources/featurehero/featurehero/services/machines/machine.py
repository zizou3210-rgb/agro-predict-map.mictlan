"""To run machine to prediction"""

import random
import time
import json
from abc import ABC, abstractmethod
from datetime import timedelta
from typing import Union


from numpy import ndarray
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import BayesianRidge, Lasso
from sklearn.svm import SVR
from xgboost import XGBRegressor
import pandas as pd

from featurehero.core.metrics.metric import Metric
from featurehero.core.metrics.metric_enums import MetricEnum
from featurehero.services.machines.machine_enums import (
    MachineNames,
    HyperTypeValueEnum,
    LimitHyperParameter,
    HyperParameterRebuild,
)


class HyperParametersDefinition:
    """General definition for hyperparameters"""

    def __init__(
        self,
        value: str,
        limit_hyper_parameter: LimitHyperParameter = LimitHyperParameter(),
        type_value: HyperTypeValueEnum = HyperTypeValueEnum.FLOAT,
    ):
        self._type_value = type_value
        self._value_str = value
        self._low_str = limit_hyper_parameter.low_value
        self._high_str = limit_hyper_parameter.high_value
        self._catalogue_values = limit_hyper_parameter.catalogue_values
        is_invalid = self._low_str is None and self._catalogue_values is None
        if is_invalid:
            raise ValueError(
                f"Not valid hyper parameter with value - {value}")

    @property
    def type_value(self) -> HyperTypeValueEnum:
        """Return the type of hyper parameter"""
        return self._type_value

    def set_value(self, value: str) -> None:
        """Set a new value on str"""
        if self._type_value == HyperTypeValueEnum.INT:
            value_number = int(value)
            value_number = max(value_number, float(self._low_str))
            value_number = min(value_number, float(self._high_str))
            self._value_str = f"{int(value_number)}"
        if self._type_value == HyperTypeValueEnum.FLOAT:
            value_number = float(value)
            value_number = max(value_number, float(self._low_str))
            value_number = min(value_number, float(self._high_str))
            self._value_str = f"{value_number}"
        if self._type_value == HyperTypeValueEnum.CATEGORY:
            if value not in self._catalogue_values:
                raise ValueError(f"Value: {value} is not on category")
            self._value_str = f"{value}"

    @property
    def value(self) -> Union[str, float, int]:
        """Return the cast to really value

        Raises:
            ValueError: Not value to return

        Returns:
            Union[str, float, int]: Value
        """
        if self._type_value == HyperTypeValueEnum.INT:
            return int(self._value_str)
        if self._type_value == HyperTypeValueEnum.FLOAT:
            return float(self._value_str)
        if self._type_value == HyperTypeValueEnum.CATEGORY:
            return self._value_str
        raise ValueError("Not value to return")

    def mutate_value(self, deep_decimal: int) -> None:
        """Mutate a value

        Args:
            deep_decimal (int): deep of decimal to mutate

        Raises:
            ValueError: _description_

        Returns:
            _type_: _description_
        """
        if self._type_value == HyperTypeValueEnum.FLOAT:
            low = float(self._low_str)
            high = float(self._high_str)
            value = round(random.uniform(low, high), deep_decimal)
            self.set_value(value=f"{value}")
        if self._type_value == HyperTypeValueEnum.INT:
            low = int(self._low_str)
            high = int(self._high_str)
            value = random.randint(low, high)
            value = int(value)
            self.set_value(value=f"{value}")
        if self._type_value == HyperTypeValueEnum.CATEGORY:
            self.set_value(value=f"{random.choice(self._catalogue_values)}")


class MachineRegression(ABC):
    """Machine for regression and prediction"""

    def __init__(self) -> None:
        self._time_training = 0
        self._machine = None
        self._machine_name: MachineNames = None
        self._error_metric = None
        self._hyper_parameters: dict[HyperParametersDefinition] = None
        self._default_hyper_parameters: dict[HyperParametersDefinition] = None
        self._rebuild_hyper_parameters: list[HyperParameterRebuild] = None

    @property
    def hyper_parameters(self) -> dict[HyperParametersDefinition]:
        """Create a random hyper parameters"""
        return self._hyper_parameters

    @property
    def machine_name(self) -> MachineNames:
        """Get the machine name by enum"""
        return self._machine_name

    @property
    def time_training(self) -> float:
        """Return time of training

        Returns:
            float: _description_
        """
        return self._time_training

    @property
    def rebuild_hyper_parameters(self) -> list[HyperParameterRebuild]:
        """Return a list of hyper parameters for rebuilding.

        Returns:
            list[HyperParameterRebuild]: list hyper parameters
        """
        return self._rebuild_hyper_parameters

    @abstractmethod
    def build_machine(self) -> None:
        """Create a machine for training and predict"""

    @abstractmethod
    def build_machine_default(self) -> None:
        """Create a machine with minimal parameters"""

    def set_rebuild_hyper_parameters(
        self, rebuild_parameters: list[HyperParameterRebuild]
    ) -> None:
        """Rebuild the machine with old parameters

        Args:
            rebuild_parameters (list[HyperParameterRebuild]): List of new
                hyper parameters
        """
        self._rebuild_hyper_parameters = rebuild_parameters
        for parameter in rebuild_parameters:
            self._hyper_parameters[parameter.name].set_value(parameter.value)

    def identity(self) -> dict:
        """Return the str that identify the machine and the features"""
        identity_dict = {
            "name": self._machine_name,
            "training_time": self._time_training,
        }
        identity_parameters = []
        for key, value in self._hyper_parameters.items():
            identity_parameters.append({"name": key, "value": value.value})
        identity_dict["parameters"] = identity_parameters
        return identity_dict

    def __str__(self):
        """Create str with name and hyper parameters"""
        return json.dumps(self.identity())

    def set_hyper_parameters(
        self,
        hyper_parameters: dict[HyperParametersDefinition],
    ) -> None:
        """Set hyper parameters to machine"""
        self._hyper_parameters = hyper_parameters

    def training(self, x_train: pd.Series, y_train: pd.Series) -> None:
        """Training function

        Args:
            x_train (pd.Series): Vector for training
            y_train (pd.Series): Vector to predict
        """
        start = time.time()
        self._machine.fit(x_train, y_train)
        self._time_training = timedelta(seconds=time.time() - start)

    def test(
        self,
        x_test: ndarray,
        y_test: ndarray,
    ) -> Metric:
        """Run test on machine and store data on error

        Args:
            x_test (ndarray): _description_
            y_test (ndarray): _description_
        """
        return Metric(
            x_test=x_test, y_test=y_test,
            y_predicted=self._machine.predict(x_test)
        )

    def prediction(self, x_test: ndarray) -> ndarray:
        """Predict new values

        Args:
            x_test (ndarray): Vector for predict

        Returns:
            ndarray: Vector predicted
        """
        return self._machine.predict(x_test)

    def force_mutate_hyper_parameters(self, deep_decimal: int) -> None:
        """Force mutate the hyper parameters

        Args:
            deep_decimal (int): Decimal to round the hyper parameters
        """
        for key, _ in self._hyper_parameters.items():
            self._hyper_parameters[key].mutate_value(
                deep_decimal=deep_decimal,
            )

    def mutate_hyper_parameters(self, mutation_rate: float, deep_decimal: int):
        """Mutate the hyper parameters

        Args:
            mutation_rate (float): Range between 0 and 1 to mutate the
                hyper parameters
        """
        for key, _ in self._hyper_parameters.items():
            if random.random() < mutation_rate:
                self._hyper_parameters[key].mutate_value(
                    deep_decimal=deep_decimal,
                )

    def set_one_hyper_parameter(self, hyper: HyperParameterRebuild) -> None:
        """Set one value on one hyper parameter

        Args:
            value (str): value to set
            key_hyper (str): key of hyper parameter
        """
        if hyper.name not in self._hyper_parameters:
            raise KeyError(f"Hyper parameter '{hyper.name}' does not exist.")
        self._hyper_parameters[hyper.name].setValue(value=hyper.value)

    def machine(self):
        """Save the machine

        Args:
            path (str): Path to save
        """
        return self._machine


class BayesianRidgeRegression(MachineRegression):
    """Class to run a Bayesian Prediction"""

    def __init__(self) -> None:
        super().__init__()
        self._machine_name = MachineNames.BAYESIAN_RIDGE_REGRESSION.value
        self._default_hyper_parameters = {}
        self._hyper_parameters = {}
        self._default_hyper_parameters = {
            "alpha_1": HyperParametersDefinition(
                value="0.000001",
                limit_hyper_parameter=LimitHyperParameter(
                    low_value="1e-6", high_value="1e-1"),
                type_value=HyperTypeValueEnum.FLOAT,
            ),
            "lambda_1": HyperParametersDefinition(
                value="0.000001",
                limit_hyper_parameter=LimitHyperParameter(
                    low_value="1e-6", high_value="1e-1"),
                type_value=HyperTypeValueEnum.FLOAT,
            ),
        }
        self._hyper_parameters = self._default_hyper_parameters

    def build_machine(self) -> None:
        self._machine = BayesianRidge(
            alpha_1=self._hyper_parameters["alpha_1"].value,
            lambda_1=self._hyper_parameters["lambda_1"].value,
        )

    def build_machine_default(self) -> None:
        self._machine = BayesianRidge()


class LassoRegression(MachineRegression):
    """Machine for linear LASSO

    Args:
        MachinePrediction (_type_): Abstract method
    """

    def __init__(self) -> None:
        super().__init__()
        self._machine_name = MachineNames.LASSO_REGRESSION.value
        self._default_hyper_parameters = {}
        self._hyper_parameters = {}
        self._default_hyper_parameters = {
            "alfa": HyperParametersDefinition(
                value="0.1",
                limit_hyper_parameter=LimitHyperParameter(
                    low_value="0.0001", high_value="0.1"),
                type_value=HyperTypeValueEnum.FLOAT,
            ),
            "selection": HyperParametersDefinition(
                value="cyclic",
                limit_hyper_parameter=LimitHyperParameter(
                    catalogue_values=["cyclic", "random"]),
                type_value=HyperTypeValueEnum.CATEGORY,
            ),
        }
        self._hyper_parameters = self._default_hyper_parameters

    def build_machine(self) -> None:
        self._machine = Lasso(
            alpha=self._hyper_parameters["alfa"].value,
            selection=self._hyper_parameters["selection"].value,
        )

    def build_machine_default(self):
        self._machine = Lasso()


class RandomForestRegression(MachineRegression):
    """Machine for Random forest

    Args:
        MachinePrediction (_type_): Abstract method
    """

    def __init__(self, metric_selection: MetricEnum = None) -> None:
        super().__init__()
        self._metric_selection = metric_selection
        self._machine_name = MachineNames.RANDOM_FOREST_REGRESSION.value
        self._default_hyper_parameters = {}
        self._hyper_parameters = {}
        self._default_hyper_parameters = {
            "n_estimators": HyperParametersDefinition(
                value="100",
                limit_hyper_parameter=LimitHyperParameter(
                    low_value="10", high_value="10000"),
                type_value=HyperTypeValueEnum.INT,
            ),
            "min_samples_split": HyperParametersDefinition(
                value="0.1",
                limit_hyper_parameter=LimitHyperParameter(
                    low_value="0.1", high_value="1"),
                type_value=HyperTypeValueEnum.FLOAT,
            ),
            "ccp_alpha": HyperParametersDefinition(
                value="0.1",
                limit_hyper_parameter=LimitHyperParameter(
                    low_value="0.1", high_value="100"),
                type_value=HyperTypeValueEnum.FLOAT,
            ),
            "max_leaf_nodes": HyperParametersDefinition(
                value="100",
                limit_hyper_parameter=LimitHyperParameter(
                    low_value="100", high_value="10000"),
                type_value=HyperTypeValueEnum.INT,
            ),
            "min_impurity_decrease": HyperParametersDefinition(
                value="0.0",
                limit_hyper_parameter=LimitHyperParameter(
                    low_value="0.0", high_value="1"),
                type_value=HyperTypeValueEnum.FLOAT,
            ),
        }
        self._hyper_parameters = self._default_hyper_parameters

    def _criterion(self) -> str:
        """Align the tree split criterion with the selected metric."""
        if self._metric_selection == MetricEnum.MEAN_ABSOLUTE_ERROR:
            return "absolute_error"
        return "squared_error"

    def build_machine(self) -> None:
        self._machine = RandomForestRegressor(
            n_estimators=self._hyper_parameters["n_estimators"].value,
            min_samples_split=self._hyper_parameters[
                "min_samples_split"].value,
            ccp_alpha=self._hyper_parameters["ccp_alpha"].value,
            max_leaf_nodes=self._hyper_parameters["max_leaf_nodes"].value,
            min_impurity_decrease=self._hyper_parameters[
                "min_impurity_decrease"].value,
            criterion=self._criterion(),
            n_jobs=-1,
        )

    def build_machine_default(self):
        self._machine = RandomForestRegressor(
            n_jobs=-1,
            n_estimators=self._hyper_parameters["n_estimators"].value,
            criterion=self._criterion(),
        )


class SupportVectorRegression(MachineRegression):
    """Machine for Support Vector Regression

    Args:
        MachinePrediction (_type_): Abstract method
    """

    def __init__(self) -> None:
        super().__init__()
        self._machine_name = MachineNames.SUPPORT_VECTOR_REGRESSION.value
        self._default_hyper_parameters = {}
        self._hyper_parameters = {}
        self._default_hyper_parameters = {
            "kernel": HyperParametersDefinition(
                value="linear",
                limit_hyper_parameter=LimitHyperParameter(
                    catalogue_values=["linear", "poly", "rbf", "sigmoid"]),
                type_value=HyperTypeValueEnum.CATEGORY,
            ),
            "degree": HyperParametersDefinition(
                value="3",
                limit_hyper_parameter=LimitHyperParameter(
                    low_value="1", high_value="10"),
                type_value=HyperTypeValueEnum.INT,
            ),
            "gama": HyperParametersDefinition(
                value="scale",
                limit_hyper_parameter=LimitHyperParameter(
                    catalogue_values=["scale", "auto"]),
                type_value=HyperTypeValueEnum.CATEGORY,
            ),
            "c": HyperParametersDefinition(
                value="1",
                limit_hyper_parameter=LimitHyperParameter(
                    low_value="0.001", high_value="1"),
                type_value=HyperTypeValueEnum.FLOAT,
            ),
            "epsilon": HyperParametersDefinition(
                value="0.1",
                limit_hyper_parameter=LimitHyperParameter(
                    low_value="0.1", high_value="10"),
                type_value=HyperTypeValueEnum.FLOAT,
            ),
            "coef0": HyperParametersDefinition(
                value="0.0",
                limit_hyper_parameter=LimitHyperParameter(
                    low_value="0.001", high_value="0"),
                type_value=HyperTypeValueEnum.FLOAT,
            ),
            "tol": HyperParametersDefinition(
                value="0.001",
                limit_hyper_parameter=LimitHyperParameter(
                    low_value="0.0001", high_value="1.0"),
                type_value=HyperTypeValueEnum.FLOAT,
            ),
        }
        self._hyper_parameters = self._default_hyper_parameters

    def build_machine(self) -> None:
        self._machine = SVR(
            kernel=self._hyper_parameters["kernel"].value,
            C=self._hyper_parameters["c"].value,
            epsilon=self._hyper_parameters["epsilon"].value,
            degree=self._hyper_parameters["degree"].value,
            gamma=self._hyper_parameters["gama"].value,
            coef0=self._hyper_parameters["coef0"].value,
            tol=self._hyper_parameters["tol"].value,
        )

    def build_machine_default(self):
        self._machine = SVR(
            kernel=self._hyper_parameters["kernel"].value,
        )


class ExtremeGradientBoostRegression(MachineRegression):
    """Machine for prediction on Extreme Gradient Boosting

    Args:
        MachinePrediction (_type_): Abstract method
    """

    def __init__(self, metric_selection: MetricEnum = None) -> None:
        super().__init__()
        self._metric_selection = metric_selection
        self._machine_name = (
            MachineNames.EXTREME_GRADIENT_BOOSTING_REGRESSION.value
        )
        self._default_hyper_parameters = {}
        self._hyper_parameters = {}
        self._default_hyper_parameters = {
            "n_estimators": HyperParametersDefinition(
                value="100",
                limit_hyper_parameter=LimitHyperParameter(
                    low_value="10", high_value="10000"),
                type_value=HyperTypeValueEnum.INT,
            ),
            "eta": HyperParametersDefinition(
                value=0.3,
                limit_hyper_parameter=LimitHyperParameter(
                    low_value="0", high_value="1"),
                type_value=HyperTypeValueEnum.FLOAT,
            ),
            "gamma": HyperParametersDefinition(
                value="0.3",
                limit_hyper_parameter=LimitHyperParameter(
                    low_value="0", high_value="1"),
                type_value=HyperTypeValueEnum.FLOAT,
            ),
            "max_depth": HyperParametersDefinition(
                limit_hyper_parameter=LimitHyperParameter(
                    low_value="0", high_value="300"),
                value="6",
                type_value=HyperTypeValueEnum.INT,
            ),
            "min_child_weight": HyperParametersDefinition(
                limit_hyper_parameter=LimitHyperParameter(
                    low_value="0", high_value="300"),
                value="1",
                type_value=HyperTypeValueEnum.INT,
            ),
            "max_delta_step": HyperParametersDefinition(
                limit_hyper_parameter=LimitHyperParameter(
                    low_value="0", high_value="300"),
                value="0",
                type_value=HyperTypeValueEnum.INT,
            ),
            "subsample": HyperParametersDefinition(
                limit_hyper_parameter=LimitHyperParameter(
                    low_value="0", high_value="1"),
                value="0",
                type_value=HyperTypeValueEnum.INT,
            ),
            "learning_rate": HyperParametersDefinition(
                limit_hyper_parameter=LimitHyperParameter(
                    low_value="0", high_value="1"),
                value="1",
                type_value=HyperTypeValueEnum.FLOAT,
            ),
            "alpha": HyperParametersDefinition(
                limit_hyper_parameter=LimitHyperParameter(
                    low_value="0.01", high_value="1"),
                value="0.01",
                type_value=HyperTypeValueEnum.FLOAT,
            ),
            "lambda": HyperParametersDefinition(
                limit_hyper_parameter=LimitHyperParameter(
                    low_value="0.01", high_value="1"),
                value="0.01",
                type_value=HyperTypeValueEnum.FLOAT,
            ),
        }
        self._hyper_parameters = self._default_hyper_parameters

    def _objective_arguments(self) -> dict[str, str]:
        """Align the boosting objective with the selected metric when possible."""
        if self._metric_selection == MetricEnum.MEAN_ABSOLUTE_ERROR:
            return {
                "objective": "reg:absoluteerror",
                "eval_metric": "mae",
            }
        return {
            "objective": "reg:squarederror",
            "eval_metric": "rmse",
        }

    def build_machine(self) -> None:
        self._machine = XGBRegressor(
            n_estimators=self._hyper_parameters["n_estimators"].value,
            eta=self._hyper_parameters["eta"].value,
            gamma=self._hyper_parameters["gamma"].value,
            max_depth=self._hyper_parameters["max_depth"].value,
            min_child_weight=self._hyper_parameters["min_child_weight"].value,
            max_delta_step=self._hyper_parameters["max_delta_step"].value,
            subsample=self._hyper_parameters["subsample"].value,
            alpha=self._default_hyper_parameters["alpha"].value,
            learning_rate=self._hyper_parameters["learning_rate"].value,
            reg_lambda=self._hyper_parameters["lambda"].value,
            **self._objective_arguments(),
            n_jobs=-1,
        )

    def build_machine_default(self):
        self._machine = XGBRegressor(
            n_estimators=self._hyper_parameters["n_estimators"].value,
            **self._objective_arguments(),
            n_jobs=-1,
        )
