"""Worker for the application"""
import traceback
import sys
from queue import Queue


from featurehero.core.files.machine_file import FileDataRegression
from featurehero.services.optimizations.optimization import (
    optimization_run_from_task,
)


def genetic_algorithm(
        progress_queue: Queue,
        selected_column: str,
        file_path: str,
        folder_file: str,
        params: dict = None,
        status_file: str | None = None,
):
    """Main worker to search the feature

    Args:
        progress_queue (Queue): Queue to send progress updates
        selected_column (str): Target column name
        file_path (str): Path to the input file
        folder_file (str): Path to the folder containing the file
        status_file (str | None): Path to the status file for progress.
    """
    try:
        progress_queue.put(0)
        optimization_run_from_task(
            file_data=FileDataRegression(
                file_in=file_path,
                target_feature=selected_column,
                folder_path=folder_file,
            ),
            importance_columns="",
            progress_queue=progress_queue,
            params=params,
            status_file=status_file,
        )
        progress_queue.put("DONE")
    except (ValueError, IOError, FileNotFoundError) as e:
        progress_queue.put(f"[ERROR] {e}")
        traceback.print_exc()
    except Exception as e:
        # Catch any other unexpected exceptions
        _, _, exc_traceback = sys.exc_info()
        # Get the last stack frame from the traceback
        tb_details = traceback.extract_tb(exc_traceback)
        last_call = tb_details[-1]
        error_message = (
            f"An unexpected error occurred in {last_call.filename} "
            f"at line {last_call.lineno}: {e}"
        )
        progress_queue.put(f"[ERROR] {error_message}")
        traceback.print_exc()
