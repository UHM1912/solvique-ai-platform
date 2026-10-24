"""
Logging configuration for Solvique.

Features:
- Colored console output per tool/layer (DEBUG=cyan, INFO=green, WARNING=yellow, ERROR=red)
- request_id stamped on every log line via contextvars
- Execution timing utilities
- File handler writing to LOG_FILE_PATH
- Root logger set to WARNING — only OUR namespaces get DEBUG
"""

import logging
import time
import sys
from contextvars import ContextVar
from typing import Optional
import os
import config
import csv
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Context variable — stores request_id for the current async task / thread
# ---------------------------------------------------------------------------
_request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def set_request_id(request_id: str) -> None:
    _request_id_var.set(request_id)


def get_request_id() -> str:
    return _request_id_var.get()


# ---------------------------------------------------------------------------
# ANSI colour codes
# ---------------------------------------------------------------------------
class _Colours:
    RESET = "\033[0m"
    GREY = "\033[90m"
    CYAN = "\033[96m"  # DEBUG
    GREEN = "\033[92m"  # INFO
    YELLOW = "\033[93m"  # WARNING
    RED = "\033[91m"  # ERROR
    MAGENTA = "\033[95m"  # CRITICAL

    # Tool-specific accent colours shown in the logger name field
    TOOL_SQL = "\033[94m"  # Blue
    TOOL_ML = "\033[95m"  # Magenta
    TOOL_INTELLIGENCE = "\033[96m"  # Cyan
    TOOL_API = "\033[92m"  # Green


_LEVEL_COLOURS = {
    logging.DEBUG: _Colours.CYAN,
    logging.INFO: _Colours.GREEN,
    logging.WARNING: _Colours.YELLOW,
    logging.ERROR: _Colours.RED,
    logging.CRITICAL: _Colours.MAGENTA,
}

_LOGGER_COLOURS = {
    "sql": _Colours.TOOL_SQL,
    "ml": _Colours.TOOL_ML,
    "intelligence": _Colours.TOOL_INTELLIGENCE,
    "api": _Colours.TOOL_API,
}


# ---------------------------------------------------------------------------
# Custom formatter — injects request_id + colours
# ---------------------------------------------------------------------------
class _RequestAwareFormatter(logging.Formatter):
    def __init__(self, use_colour: bool = True) -> None:
        super().__init__()
        self.use_colour = use_colour

    def format(self, record: logging.LogRecord) -> str:
        request_id = get_request_id()

        name_colour = _Colours.GREY
        for key, colour in _LOGGER_COLOURS.items():
            if key in record.name.lower():
                name_colour = colour
                break

        level_colour = _LEVEL_COLOURS.get(record.levelno, _Colours.RESET)
        timestamp = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        level_name = f"{record.levelname:<8}"
        message = record.getMessage()

        exc_text = ""
        if record.exc_info:
            exc_text = "\n" + self.formatException(record.exc_info)

        if self.use_colour:
            return (
                f"{_Colours.GREY}{timestamp}{_Colours.RESET} "
                f"{level_colour}[{level_name}]{_Colours.RESET} "
                f"{name_colour}[{record.name}]{_Colours.RESET} "
                f"{_Colours.GREY}[req:{request_id}]{_Colours.RESET} "
                f"{message}"
                f"{_Colours.RED}{exc_text}{_Colours.RESET}"
            )
        else:
            return (
                f"{timestamp} [{level_name}] [{record.name}] "
                f"[req:{request_id}] {message}{exc_text}"
            )


# ---------------------------------------------------------------------------
# Logger factory
# ---------------------------------------------------------------------------
_initialised = False

# Our own application namespaces — these get DEBUG level
# Everything else (urllib3, watchfiles, asyncio, etc.) inherits WARNING from root
_OUR_NAMESPACES = (
    "src",
    "main",
    "core",
    "intelligence",
    "tools",
    "api",
    "app",
    "intent_classifier",
    "ml_tool",
    "sql_main",
    "fetch_schema",
    "execute_sql_query",
    "logging_config",
    "__main__",
    "graph",
)


def _initialise_root_logger() -> None:
    global _initialised
    if _initialised:
        return
    _initialised = True

    # Root = WARNING — all third-party libraries inherit this and stay quiet
    root = logging.getLogger()
    root.setLevel(logging.WARNING)

    # Our namespaces get full DEBUG visibility
    for namespace in _OUR_NAMESPACES:
        logging.getLogger(namespace).setLevel(logging.DEBUG)

    # --- Console handler (coloured) ---
    console_handler = logging.StreamHandler(sys.__stdout__)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(_RequestAwareFormatter(use_colour=True))
    root.addHandler(console_handler)

    # --- File handler (plain text, no colour) ---
    try:
        log_path = config.LOG_FILE_PATH

        log_dir = os.path.dirname(log_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        if not os.path.exists(log_path):
            with open(log_path, "w", encoding="utf-8") as f:
                pass  # just create empty file

        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(_RequestAwareFormatter(use_colour=False))
        root.addHandler(file_handler)

    except Exception as exc:
        root.warning("Could not open log file %s: %s", config.LOG_FILE_PATH, exc)


def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger. Call once per module:

        logger = get_logger(__name__)
    """
    _initialise_root_logger()
    return logging.getLogger(name)


_TRACE_COLUMNS = [
    "timestamp",
    "request_id",
    "component",
    "duration_s",
]


def _trace_file_path() -> Path:
    return Path(config.LOG_FILE_PATH).parent / "component_timings.csv"


def write_trace_row(
    *,
    component: str,
    duration_s: float,
) -> None:
    path = _trace_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = path.exists()

    with path.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=_TRACE_COLUMNS)

        if not file_exists:
            writer.writeheader()

        writer.writerow(
            {
                "timestamp": datetime.utcnow().isoformat(),
                "request_id": get_request_id(),
                "component": component,
                "duration_s": round(duration_s, 2),
            }
        )


# ---------------------------------------------------------------------------
# Timing utilities
# ---------------------------------------------------------------------------
class Timer:
    """
    Lightweight context-manager / manual timer.

    Usage (context manager)::

        with Timer("sql_query_generation") as t:
            ...
        logger.info("Step took %.3fs", t.elapsed)

    Usage (manual)::

        t = Timer("model_predict").start()
        ...
        elapsed = t.stop()
    """

    def __init__(self, label: str) -> None:
        self.label = label
        self.elapsed: float = 0.0
        self._start: Optional[float] = None

    def start(self) -> "Timer":
        self._start = time.perf_counter()
        return self

    def stop(self) -> float:
        if self._start is None:
            raise RuntimeError("Timer.stop() called before Timer.start()")
        self.elapsed = time.perf_counter() - self._start
        return self.elapsed

    def __enter__(self) -> "Timer":
        return self.start()

    def __exit__(self, *_) -> None:
        self.stop()
        try:
            write_trace_row(
                component=self.label,
                duration_s=self.elapsed,
            )
        except Exception:
            pass
