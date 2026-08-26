#!/usr/bin/env python3
import argparse
import logging
import msvcrt
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
LOG_FILE = LOG_DIR / "realtime.log"
LOCK_FILE = ROOT / ".realtime-runner.lock"
CHANGED_FILE = ROOT / ".changed"
INTERVAL_MINUTES = 5
BOUNDARY_DELAY_SECONDS = 5
RETRY_SECONDS = 15
MAX_GENERATION_ATTEMPTS = 4


def configure_logging():
    LOG_DIR.mkdir(exist_ok=True)
    formatter = logging.Formatter("%(asctime)sZ %(levelname)s %(message)s")
    formatter.converter = time.gmtime

    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=2_000_000,
        backupCount=4,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])


def acquire_lock():
    lock_handle = LOCK_FILE.open("a+b")
    try:
        if LOCK_FILE.stat().st_size == 0:
            lock_handle.write(b"0")
            lock_handle.flush()
        lock_handle.seek(0)
        msvcrt.locking(lock_handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        lock_handle.close()
        raise RuntimeError("Another real-time runner is already active.")
    return lock_handle


def run(command, check=True):
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.stdout.strip():
        logging.info(completed.stdout.strip())
    if completed.stderr.strip():
        log = logging.info if completed.returncode == 0 else logging.warning
        log(completed.stderr.strip())
    if check and completed.returncode != 0:
        raise RuntimeError(
            f"Command failed ({completed.returncode}): {' '.join(map(str, command))}"
        )
    return completed


def next_boundary(now=None):
    now = now or datetime.now(timezone.utc)
    minute = now.minute - (now.minute % INTERVAL_MINUTES)
    boundary = now.replace(minute=minute, second=BOUNDARY_DELAY_SECONDS, microsecond=0)
    if boundary <= now:
        boundary += timedelta(minutes=INTERVAL_MINUTES)
    return boundary


def generate_current_slot():
    for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
        result = run([sys.executable, str(ROOT / "dice_poker.py")], check=False)
        if result.returncode == 0:
            return True
        if attempt < MAX_GENERATION_ATTEMPTS:
            logging.warning(
                "Generation attempt %d failed; retrying in %d seconds.",
                attempt,
                RETRY_SECONDS,
            )
            time.sleep(RETRY_SECONDS)
    logging.error("Generation failed after %d attempts.", MAX_GENERATION_ATTEMPTS)
    return False


def push_pending_commits():
    ahead = run(
        ["git", "rev-list", "--count", "@{upstream}..HEAD"],
        check=False,
    )
    if ahead.returncode != 0 or ahead.stdout.strip() == "0":
        return

    result = run(["git", "push", "origin", "main"], check=False)
    if result.returncode != 0:
        logging.error("Git push failed. The local commit is preserved for the next retry.")


def commit_changes():
    if not CHANGED_FILE.exists():
        return

    CHANGED_FILE.unlink(missing_ok=True)
    run(["git", "add", "data/"])
    status = run(["git", "status", "--porcelain", "--", "data/"], check=False)
    if not status.stdout.strip():
        logging.info("No uncommitted data changes remain.")
        return

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    run(["git", "config", "user.name", "wnba-dice-poker-local"])
    run(
        [
            "git",
            "config",
            "user.email",
            "wnba-dice-poker-local@users.noreply.github.com",
        ]
    )
    run(["git", "commit", "-m", f"Add real-time Dice Poker result {timestamp}"])


def run_cycle():
    logging.info("Starting five-minute collection cycle.")
    if generate_current_slot():
        commit_changes()
        push_pending_commits()


def main():
    parser = argparse.ArgumentParser(description="Run WNBA Dice Poker in real time.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one collection cycle and exit.",
    )
    args = parser.parse_args()

    configure_logging()
    try:
        lock_handle = acquire_lock()
    except RuntimeError as exc:
        logging.error(str(exc))
        return 1

    with lock_handle:
        logging.info("Real-time runner started with Python %s.", sys.version.split()[0])
        if args.once:
            run_cycle()
            return 0

        while True:
            wake_at = next_boundary()
            wait_seconds = max(0, (wake_at - datetime.now(timezone.utc)).total_seconds())
            logging.info("Next collection cycle: %s", wake_at.isoformat())
            time.sleep(wait_seconds)
            try:
                run_cycle()
            except Exception:
                logging.exception("Unexpected cycle failure; runner will continue.")


if __name__ == "__main__":
    raise SystemExit(main())
