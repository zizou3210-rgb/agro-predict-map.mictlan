"""Functions for data transformation tasks."""
import os
import math
import pandas as pd


def _read_file(file_path: str) -> pd.DataFrame:
    """Reads a file into a pandas DataFrame based on its extension."""
    _, file_extension = os.path.splitext(file_path)
    if file_extension.lower() == '.csv':
        return pd.read_csv(file_path)
    if file_extension.lower() in ['.xls', '.xlsx']:
        return pd.read_excel(file_path)
    # Note: .numbers support is more complex and is omitted here for brevity.
    # It would require logic similar to work_space_file.py
    raise ValueError(f"Unsupported file type: {file_extension}")


def _transform_date_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Expand date columns into numeric date parts."""
    for col in columns:
        date_col = pd.to_datetime(df[col], errors='coerce')
        df[f'{col}_year'] = date_col.dt.year
        df[f'{col}_month'] = date_col.dt.month
        df[f'{col}_day'] = date_col.dt.day
        df[f'{col}_dayofweek'] = date_col.dt.dayofweek
        df[f'{col}_dayofyear'] = date_col.dt.dayofyear
        df = df.drop(columns=[col])
    return df


def _transform_date_seasonal_columns(
    df: pd.DataFrame,
    columns: list[str],
) -> pd.DataFrame:
    """Transform MM/yyyy columns into year and month dummy variables."""
    for col in columns:
        date_col = pd.to_datetime(df[col], format='%m/%Y', errors='coerce')

        year_labels = date_col.dt.year.apply(
            lambda value: f'year_{int(value)}' if pd.notna(value) else pd.NA
        )
        month_labels = date_col.dt.month.apply(
            lambda value: f'month_{int(value):02d}' if pd.notna(value) else pd.NA
        )

        year_dummies = pd.get_dummies(
            year_labels,
            prefix=col,
            prefix_sep='_',
            dummy_na=False,
            dtype=int,
        )
        month_dummies = pd.get_dummies(
            month_labels,
            prefix=col,
            prefix_sep='_',
            dummy_na=False,
            dtype=int,
        )
        df = pd.concat(
            [df.drop(columns=[col]), year_dummies, month_dummies],
            axis=1,
        )
    return df


def _transform_log1p_columns(
    df: pd.DataFrame,
    columns: list[str],
) -> pd.DataFrame:
    """Add log1p-transformed copies of numeric columns."""
    for col in columns:
        numeric_col = pd.to_numeric(df[col], errors='coerce')
        invalid_mask = df[col].notna() & numeric_col.isna()
        if invalid_mask.any():
            raise ValueError(
                f"Column '{col}' contains non-numeric values and cannot "
                "be transformed with 'log1p'."
            )

        negative_mask = numeric_col < 0
        if negative_mask.any():
            raise ValueError(
                f"Column '{col}' contains negative values and cannot "
                "be transformed with 'log1p'."
            )

        df[f'{col}_log1p'] = numeric_col.apply(
            lambda value: math.log1p(value) if pd.notna(value) else pd.NA
        )
    return df


def _transform_sqrt_columns(
    df: pd.DataFrame,
    columns: list[str],
) -> pd.DataFrame:
    """Add square-root-transformed copies of numeric columns."""
    for col in columns:
        numeric_col = pd.to_numeric(df[col], errors='coerce')
        invalid_mask = df[col].notna() & numeric_col.isna()
        if invalid_mask.any():
            raise ValueError(
                f"Column '{col}' contains non-numeric values and cannot "
                "be transformed with 'sqrt'."
            )

        negative_mask = numeric_col < 0
        if negative_mask.any():
            raise ValueError(
                f"Column '{col}' contains negative values and cannot "
                "be transformed with 'sqrt'."
            )

        df[f'{col}_sqrt'] = numeric_col.apply(
            lambda value: math.sqrt(value) if pd.notna(value) else pd.NA
        )
    return df


def transform_data(file_path: str, transform_type: str, columns: list[str],
                   out_filename: str | None):
    """
    Transforms data in a file based on the specified type and columns.

    Args:
        file_path (str): Path to the input data file.
        transform_type (str): The type of transformation
                              to apply ('date', 'date_seasonal',
                              'category', 'dummy', 'log1p', or 'sqrt').
        columns (list[str]): A list of column names to transform.
        out_filename (str | None): New name for the output file. If None, a
                                   default name is generated.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    df = _read_file(file_path)

    # Validate that all specified columns exist in the DataFrame
    missing_cols = [col for col in columns if col not in df.columns]
    if missing_cols:
        raise ValueError(
            f"The following columns were not found in the file: "
            f"{', '.join(missing_cols)}")

    if transform_type == 'date':
        df = _transform_date_columns(df, columns)
        print(
            f"Applied 'date' transformation to columns: {', '.join(columns)}")
    elif transform_type == 'date_seasonal':
        df = _transform_date_seasonal_columns(df, columns)
        print(
            "Applied 'date_seasonal' (MM/yyyy to year/month dummy variables) "
            f"transformation to columns: {', '.join(columns)}"
        )

    elif transform_type == 'category':
        for col in columns:
            # Convert column to categorical
            # and get integer codes (starts from 0)
            # We add 1 to make it start from 1 as requested.
            df[f'{col}_number'] = pd.Categorical(df[col]).codes + 1
            df = df.drop(columns=[col])
        print(
            "Applied 'category' (label encoding) transformation to columns: "
            f"{', '.join(columns)}"
        )
    elif transform_type == 'dummy':
        for col in columns:
            dummy_df = pd.get_dummies(
                df[col],
                prefix=col,
                prefix_sep='_',
                dummy_na=False,
                dtype=int,
            )
            df = pd.concat([df.drop(columns=[col]), dummy_df], axis=1)
        print(
            "Applied 'dummy' (one-hot encoding) transformation to columns: "
            f"{', '.join(columns)}"
        )
    elif transform_type == 'log1p':
        df = _transform_log1p_columns(df, columns)
        print(
            "Applied 'log1p' (natural log of x + 1) transformation to "
            f"columns: {', '.join(columns)}"
        )
    elif transform_type == 'sqrt':
        df = _transform_sqrt_columns(df, columns)
        print(
            "Applied 'sqrt' (square root) transformation to columns: "
            f"{', '.join(columns)}"
        )
    else:
        raise ValueError(
            "Unsupported transform type. Allowed values are: "
            "'date', 'date_seasonal', 'category', 'dummy', 'log1p', "
            "'sqrt'."
        )

    # Determine output filename and path
    if out_filename is None:
        base, _ = os.path.splitext(os.path.basename(file_path))
        out_filename = f"{base}_transformed.csv"

    # Ensure output is saved as .csv for consistency
    if not out_filename.lower().endswith('.csv'):
        out_filename += '.csv'

    output_dir = os.path.dirname(file_path)
    out_path = os.path.join(output_dir, out_filename)

    df.to_csv(out_path, index=False)
    print(f"Transformed file saved to: {out_path}")
