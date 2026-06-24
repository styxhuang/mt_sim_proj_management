"""
Poll running jobs and print status updates.

Usage:
    python poll_jobs.py                    # poll all running jobs
    python poll_jobs.py --project_id 154   # filter by project (default: BOHRIUM_PROJECT_ID)
    python poll_jobs.py --interval 30      # check every 30 seconds
"""

import json
import os
import subprocess
import time
from datetime import datetime


def get_jobs(status_flag: str | None = None, project_id: int | None = None) -> list[dict]:
    """Get job list as JSON."""
    cmd = ["bohr", "job", "list", "-n", "20", "--json"]
    if status_flag:
        cmd.append(status_flag)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return []
    try:
        jobs = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    if project_id is None:
        return jobs
    return [
        job
        for job in jobs
        if str(job.get("projectId", job.get("project_id", ""))) == str(project_id)
    ]


def format_status(status: str) -> str:
    icons = {
        "Running": "RUN",
        "Finished": "OK ",
        "Failed": "ERR",
        "Pending": "...",
        "Scheduling": "...",
    }
    return icons.get(status, status)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Poll Bohrium job status")
    default_project_id = int(os.environ.get("BOHRIUM_PROJECT_ID", "0") or "0") or None
    parser.add_argument(
        "--project_id",
        type=int,
        default=default_project_id,
        help="Filter by project ID (default: BOHRIUM_PROJECT_ID)",
    )
    parser.add_argument("--interval", type=int, default=60, help="Poll interval in seconds")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    args = parser.parse_args()

    while True:
        now = datetime.now().strftime("%H:%M:%S")
        jobs = get_jobs("-r", args.project_id)  # running only
        pending = get_jobs("-p", args.project_id)  # pending
        all_active = jobs + pending

        if not all_active:
            print(f"[{now}] No active jobs.")
            if args.once:
                break
            time.sleep(args.interval)
            continue

        print(f"\n[{now}] Active jobs: {len(all_active)}")
        print(f"  {'ID':<12} {'Status':<6} {'Name':<30}")
        print(f"  {'-'*12} {'-'*6} {'-'*30}")
        for job in all_active:
            job_id = job.get("jobId", job.get("id", "?"))
            status = format_status(job.get("status", "?"))
            name = job.get("jobName", job.get("name", "?"))[:30]
            print(f"  {job_id:<12} {status:<6} {name}")

        if args.once:
            break

        print(f"  Next check in {args.interval}s... (Ctrl+C to stop)")
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nStopped.")
            break


if __name__ == "__main__":
    main()
