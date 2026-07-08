"""Create modules and presentation of results"""

import matplotlib.pyplot as plt
import seaborn as sns

from featurehero.core.files.access_file import StorageFile


def create_graph_model_index(
        file_result: str,
        folder: str,
        prefix: str = "result",
        limit_rows: int = 0,
):
    """Create image with graphic of model and metric result

    Args:
        file_result (str): file of result
    """
    plt.switch_backend('Agg')
    store = StorageFile(file_name=file_result, folder_file=folder)
    df = store.get_csv_to_data_frame()
    if limit_rows > 0:
        df = df.head(limit_rows)
    plt.figure(figsize=(10, 6))
    sns.scatterplot(data=df, x=df.index, y="index_metric", hue="machine_name")
    plt.title("Model and Metric Result")
    plt.xlabel("Index")
    plt.ylabel("Metric")
    file_to_save = store.adding_prefix_name_extension(
        prefix=f"{prefix}_graph",
        extension="png",
    )
    plt.savefig(file_to_save)
    plt.close()
