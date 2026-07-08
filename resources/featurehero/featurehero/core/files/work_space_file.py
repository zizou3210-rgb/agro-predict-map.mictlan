"""Basic function to work with a file on work space
    """
import datetime
import os

import pandas as pd
from numbers_parser import Document


def prepare_work_space_file(
        file_path: str,
        target_column: str
) -> tuple[str, str]:
    """Prepare the work space file according to the file path
    Args:
        file_path (str): path to file
        target_column (str): target column name

    Returns:
        tuple[str, str]: The full path to the new file and the file name.
    """
    allowed_extensions = ['.numbers', '.csv', '.xls', '.xlsx']
    if (file_path is None) or (file_path == ""):
        raise ValueError("File path is empty or None")
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File {file_path} not found")
    _, file_extension = os.path.splitext(file_path)
    if file_extension.lower() not in allowed_extensions:
        raise ValueError(
            f"File extension '{file_extension}' is not supported. "
            f"Allowed extensions are: {', '.join(allowed_extensions)}"
        )
    new_folder = os.path.join(
        os.path.dirname(file_path),
        "work_space_featurehero",
        datetime.datetime.now().strftime("%Y%m%d_%H%M%S"),
    )
    os.makedirs(new_folder, exist_ok=True)
    new_file_name = "original.csv"
    new_file_path = os.path.join(new_folder, new_file_name)
    df = None
    if file_extension.lower() == '.csv':
        df = pd.read_csv(file_path)
    elif file_extension.lower() in ['.xls', '.xlsx']:
        xls = pd.ExcelFile(file_path)
        if len(xls.sheet_names) > 1:
            raise ValueError(
                "Excel file has multiple sheets. Please provide a file "
                "with a single sheet."
            )
        df = pd.read_excel(file_path)
    elif file_extension.lower() == '.numbers':
        doc = Document(file_path)
        if len(doc.sheets) > 1:
            raise ValueError(
                "Numbers file has multiple sheets. Please provide a file "
                "with a single sheet."
            )
        # Assuming the data is in the first table of the first sheet
        table = doc.sheets[0].tables[0]
        df = pd.DataFrame(table.rows(values_only=True))
        df.columns = df.iloc[0]
        # Strip whitespace from column names and reset index
        df.columns = df.columns.str.strip()
        df = df[1:]

    df.columns = df.columns.str.strip()
    validate = _validate_file_type(df=df, target_column=target_column)
    if validate != "":
        raise ValueError(
            f"Error validating file: {validate}"
        )
    df.to_csv(new_file_path, index=False)
    return new_folder, new_file_name


def _validate_file_type(df: pd.DataFrame, target_column: str) -> str:
    """Validate that all columns in the file are numeric.
    Args:
        df (pd.DataFrame): DataFrame to validate.
        target_column (str): Name of the target column.

    Returns:
        str: An empty string if valid, or a specific error message
             for date, text, or target column issues.
    """
    try:
        errors = []

        # 3. Validate the target column existence.
        if target_column not in df.columns:
            # This is a critical error, can't continue
            # if the target is missing.
            return f"Target column '{target_column}' not found in the file."

        # Exclude the target column from feature data type validations
        feature_columns = df.columns.drop(target_column, errors='ignore')
        df_features = df[feature_columns]

        # 1. Validate that feature columns are not of date type.
        date_columns = df_features.select_dtypes(
            include=['datetime64']).columns.tolist()
        if date_columns:
            errors.append(
                f"columns cannot be of date type: {', '.join(date_columns)}")

        # 2. Validate that feature columns are not of text type.
        text_columns = df_features.select_dtypes(
            include=['object']).columns.tolist()
        if text_columns:
            errors.append(
                f"columns cannot be of text type: {', '.join(text_columns)}")

        # 4. Validate that the target column is numeric and its values are > 0.
        if not pd.api.types.is_numeric_dtype(df[target_column]):
            errors.append(f"target column '{target_column}' must be numeric")
        elif not (df[target_column] > 0).all():
            errors.append(
                f"all values in target column '{target_column}' must be > 0")

        return "; ".join(errors)
    except (KeyError, TypeError) as e:
        return f"Error validating the file: {e}"
