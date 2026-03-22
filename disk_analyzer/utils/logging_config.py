import logging
import os
import sys
from datetime import datetime


LOG_DIR = os.path.join(os.path.expanduser("~"), ".diskanalyzer", "logs")


def setup_logging(level=logging.DEBUG):
    """Configure logging to file, console, and debug output.

    - File: ~/.diskanalyzer/logs/diskanalyzer_YYYY-MM-DD.log (DEBUG level)
    - Console/stderr: INFO level
    """
    os.makedirs(LOG_DIR, exist_ok=True)

    log_file = os.path.join(
        LOG_DIR, f"diskanalyzer_{datetime.now().strftime('%Y-%m-%d')}.log"
    )

    root = logging.getLogger("diskanalyzer")
    root.setLevel(level)

    # Avoid duplicate handlers on repeated calls
    if root.handlers:
        return root

    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    # File handler — captures everything (DEBUG+)
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # Console handler — INFO+
    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    root.info("Logging initialised  (file: %s)", log_file)
    return root


def get_logger(name):
    """Return a child logger under the 'diskanalyzer' namespace."""
    return logging.getLogger(f"diskanalyzer.{name}")
