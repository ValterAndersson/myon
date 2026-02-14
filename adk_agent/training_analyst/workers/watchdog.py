"""Watchdog entry point."""

from workers.analyst_worker import run_watchdog

if __name__ == "__main__":
    run_watchdog()
