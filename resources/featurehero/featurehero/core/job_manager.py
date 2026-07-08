"""Basic option to stop or run proccess"""
import os
import json
import datetime
import psutil


class JobManager:
    """Manages background jobs by tracking their PIDs."""

    def __init__(self):
        self.home_dir = os.path.expanduser("~")
        self.config_dir = os.path.join(self.home_dir, ".featurehero")
        self.pid_file = os.path.join(self.config_dir, "jobs.pids")
        self._ensure_config_dir()

    def _ensure_config_dir(self):
        """Ensures the configuration directory exists."""
        os.makedirs(self.config_dir, exist_ok=True)

    def _read_jobs(self):
        """Reads the list of jobs from the PID file."""
        if not os.path.exists(self.pid_file):
            return {}
        try:
            with open(self.pid_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _write_jobs(self, jobs):
        """Writes the list of jobs to the PID file."""
        with open(self.pid_file, 'w', encoding='utf-8') as f:
            json.dump(jobs, f, indent=4)

    def register_job(
        self,
        pid,
        file_path,
        target_column,
        log_file,
        status_file,
    ):
        """Registers a new background job."""
        jobs = self._read_jobs()
        jobs[str(pid)] = {
            "start_time": datetime.datetime.now().isoformat(),
            "file_path": file_path,
            "target_column": target_column,
            "log_file": log_file,
            "status_file": status_file,
        }
        self._write_jobs(jobs)

    def deregister_job(self, pid):
        """Removes a job from the registry."""
        jobs = self._read_jobs()
        if str(pid) in jobs:
            del jobs[str(pid)]
            self._write_jobs(jobs)

    def list_jobs(self):
        """Lists all currently running background jobs."""
        jobs = self._read_jobs()
        active_jobs = {}

        if not jobs:
            print("No background jobs are currently registered.")
            return

        print(
            f"{'PID':<10} {'START_TIME':<28} {'PROGRESS':<15} {'FILE':<30} {'COLUMN'}")
        print("-" * 95)

        for pid, info in jobs.items():
            if psutil.pid_exists(int(pid)):
                active_jobs[pid] = info
                start_time = info.get('start_time', 'N/A')
                file_path = os.path.basename(info.get('file_path', 'N/A'))
                column = info.get('target_column', 'N/A')
                status_file = info.get('status_file')
                progress = "N/A"
                if status_file and os.path.exists(status_file):
                    try:
                        with open(status_file, 'r', encoding='utf-8') as f:
                            progress = f.read().strip()
                    except IOError:
                        progress = "Error"

                print(f"{pid:<10} {start_time:<28} {progress:<15} "
                      f"{file_path:<30} {column}")

        if not active_jobs:
            print(
                "No active background jobs found."
                " Cleaning up stale entries."
            )

        # Clean up stale entries
        self._write_jobs(active_jobs)

    def stop_job(self, pid):
        """Stops a specific background job by its PID."""
        jobs = self._read_jobs()
        pid_str = str(pid)

        if pid_str not in jobs:
            print(f"Error: Job with PID {pid} is not registered.")
            return

        try:
            process = psutil.Process(pid)
            process.terminate()  # or process.kill()
            print(f"Termination signal sent to job with PID {pid}.")
        except psutil.NoSuchProcess:
            print(f"Job with PID {pid} is no longer running.")
        except psutil.AccessDenied:
            print(f"Error: Access denied to terminate process {pid}.")

        # Remove from registry regardless of whether it was running
        self.deregister_job(pid)
