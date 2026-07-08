"""Clean data from outlier """

from scipy import stats
import pandas as pd


def get_outlier_zscore_new_column(
    df: pd.DataFrame, target_column: str
) -> pd.DataFrame:
    """Get the outlier by zscore and return on the data frame like a
        new column with name zscore_outlier

    Args:
        df (pd.DataFrame): data frame to work on it
        target_column (str): target column to search the outlier

    Returns:
        pd.DataFrame: data frame with new column zscore_outlier
    """

    df["zscore_outlier"] = stats.zscore(df[target_column])
    return df


def remove_column_by_zscore(
    df: pd.DataFrame, target_column: str, outlier_threshold: float = 3.0
) -> pd.DataFrame:
    """Remove column by outlier column

    Args:
        df (_type_): dataset
        target_column (str): column target

    Returns:
        pd.DataFrame: data frame with out outlier rows
    """
    outliers_zscore = get_outlier_zscore_new_column(df, target_column)
    outliers_zscore = df[~(abs(outliers_zscore["zscore_outlier"]) > outlier_threshold)]
    print(f"Original row: {len(df)}, new row: {len(outliers_zscore)}")
    outliers_zscore = outliers_zscore.drop("zscore_outlier", axis=1)
    return outliers_zscore
