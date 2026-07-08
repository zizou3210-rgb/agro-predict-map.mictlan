from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from cimmyt_app.config_env import (
    get_featurehero_settings,
    get_prediction_bridge_dev_row_limit,
    get_preprocess_validation_enabled,
    get_training_results_download_dev_enabled,
    load_app_env,
    update_featurehero_settings,
)


class ConfigEnvTest(unittest.TestCase):
    def test_get_preprocess_validation_enabled_reads_false_from_env_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="app_env_test_") as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("APP_ENABLE_PREPROCESS_VALIDATION=0\n", encoding="utf-8")
            previous_value = os.environ.pop("APP_ENABLE_PREPROCESS_VALIDATION", None)
            try:
                load_app_env(env_path)
                self.assertFalse(get_preprocess_validation_enabled())
            finally:
                if previous_value is None:
                    os.environ.pop("APP_ENABLE_PREPROCESS_VALIDATION", None)
                else:
                    os.environ["APP_ENABLE_PREPROCESS_VALIDATION"] = previous_value

    def test_get_preprocess_validation_enabled_accepts_true_override(self) -> None:
        previous_value = os.environ.get("APP_ENABLE_PREPROCESS_VALIDATION")
        try:
            os.environ["APP_ENABLE_PREPROCESS_VALIDATION"] = "1"
            self.assertTrue(get_preprocess_validation_enabled())
        finally:
            if previous_value is None:
                os.environ.pop("APP_ENABLE_PREPROCESS_VALIDATION", None)
            else:
                os.environ["APP_ENABLE_PREPROCESS_VALIDATION"] = previous_value

    def test_get_training_results_download_dev_enabled_reads_true_from_env_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="config_env_") as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("APP_DEV_ENABLE_TRAINING_RESULTS_DOWNLOAD=1\n", encoding="utf-8")
            previous_value = os.environ.pop("APP_DEV_ENABLE_TRAINING_RESULTS_DOWNLOAD", None)
            try:
                load_app_env(env_path)
                self.assertTrue(get_training_results_download_dev_enabled())
            finally:
                if previous_value is None:
                    os.environ.pop("APP_DEV_ENABLE_TRAINING_RESULTS_DOWNLOAD", None)
                else:
                    os.environ["APP_DEV_ENABLE_TRAINING_RESULTS_DOWNLOAD"] = previous_value

    def test_get_prediction_bridge_dev_row_limit_reads_integer_from_env_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="config_env_") as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("APP_DEV_PREDICTION_BRIDGE_ROW_LIMIT=300\n", encoding="utf-8")
            previous_value = os.environ.pop("APP_DEV_PREDICTION_BRIDGE_ROW_LIMIT", None)
            try:
                load_app_env(env_path)
                self.assertEqual(get_prediction_bridge_dev_row_limit(), 300)
            finally:
                if previous_value is None:
                    os.environ.pop("APP_DEV_PREDICTION_BRIDGE_ROW_LIMIT", None)
                else:
                    os.environ["APP_DEV_PREDICTION_BRIDGE_ROW_LIMIT"] = previous_value

    def test_update_featurehero_settings_updates_only_allowed_env_keys(self) -> None:
        with tempfile.TemporaryDirectory(prefix="featurehero_env_") as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "APP_ENABLE_PREPROCESS_VALIDATION=0\n"
                "APP_FEATUREHERO_NUMBER_GENERATION=10\n"
                "APP_FEATUREHERO_NUMBER_POPULATION=10\n"
                "APP_FEATUREHERO_MACHINES=[\"extreme_gradient_boost_regression\"]\n"
                "APP_FEATUREHERO_METRIC=mean_absolute_error\n",
                encoding="utf-8",
            )
            previous_values = {
                key: os.environ.get(key)
                for key in (
                    "APP_FEATUREHERO_NUMBER_GENERATION",
                    "APP_FEATUREHERO_NUMBER_POPULATION",
                    "APP_FEATUREHERO_MACHINES",
                    "APP_FEATUREHERO_METRIC",
                )
            }
            try:
                update_featurehero_settings(
                    {
                        "number_generation": 20,
                        "number_population": 30,
                        "machines": [
                            "extreme_gradient_boost_regression",
                            "random_forest_regression",
                        ],
                        "metric": "root_mean_squared_error",
                        "nasa_power_resolution_km": 5,
                    },
                    env_file=env_path,
                )
                load_app_env(env_path)
                settings = get_featurehero_settings()
                self.assertEqual(settings["number_generation"], 20)
                self.assertEqual(settings["number_population"], 30)
                self.assertEqual(
                    settings["machines"],
                    ["extreme_gradient_boost_regression", "random_forest_regression"],
                )
                self.assertEqual(settings["metric"], "root_mean_squared_error")
                env_text = env_path.read_text(encoding="utf-8")
                self.assertIn("APP_ENABLE_PREPROCESS_VALIDATION=0", env_text)
                self.assertIn("APP_FEATUREHERO_NUMBER_GENERATION=20", env_text)
                self.assertIn("APP_FEATUREHERO_NUMBER_POPULATION=30", env_text)
                self.assertIn("APP_FEATUREHERO_JOB_TIMEOUT_SECONDS=", env_text)
            finally:
                for key, value in previous_values.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
