import copy

import numpy as np
import pandas as pd


class LoggerMixin:
    """
    Mixin that lets controllers log stored values once per step.

    Store each value to log with ``self.store("name", value)``, including attributes
    (e.g. ``self.store("x", self.x)``) and local variables in compute_controls.

    log() appends one row (time and stored values) to an in-memory cache and then calls log() on
    its sub-loggers: loggers held as attributes, directly or in lists or tuples (e.g. a
    supervisor's component controllers). Use get_log()
    or write_log() to retrieve the results.
    """

    def __init__(self):
        self._log_row = {}
        self._log_cache = []

    def store(self, name, value):
        """
        Store a value for the next logged row.

        Repeated calls with the same name replace the pending value.
        """
        # Copy so that later in-place changes (e.g. to arrays) don't alter logged values
        self.__dict__.setdefault("_log_row", {})[name] = (
            value
            if isinstance(value, (int, float, complex, str, bytes, type(None), np.number, np.bool_))
            else copy.deepcopy(value)
        )

    def log(self, time=None):
        """Append the current stored values to the log cache, then log sub-loggers."""
        for logger in self._logger_tree():
            row = {"time": time}
            row.update(logger.__dict__.get("_log_row", {}))
            # Clear the pending row after committing it to the log cache
            logger._log_row = {}
            if len(row) > 1:
                logger.__dict__.setdefault("_log_cache", []).append(row)

    def get_log(self):
        """
        Return this logger's and its sub-loggers' logs, outer-joined on time.

        Signal columns are prefixed with the originating controller's cname.
        Combining nonempty logs requires unique timestamps in each log.
        """
        combined = pd.DataFrame()
        for logger in self._logger_tree():
            log = pd.DataFrame(logger.__dict__.get("_log_cache", []))
            if log.empty:
                continue
            prefix = logger.cname
            log = log.rename(
                columns={name: f"{prefix}.{name}" for name in log.columns if name != "time"}
            )
            if combined.empty:
                combined = log
                continue
            overlap = (set(combined.columns) & set(log.columns)) - {"time"}
            if overlap:
                raise ValueError(f"Duplicate log columns: {sorted(overlap)}. Use distinct cnames.")
            combined = combined.merge(log, on="time", how="outer", validate="one_to_one")
        return combined

    def write_log(self, filename, output_type="pickle"):
        """Write this logger's and its sub-loggers' combined logs to a file."""
        if output_type == "pickle":
            self.get_log().to_pickle(filename)
        elif output_type == "csv":
            self.get_log().to_csv(filename, index=False)
        else:
            raise ValueError(f"Unsupported output_type: {output_type}")

    def reset_log(self):
        """Reset this logger's and its sub-loggers' logs."""
        for logger in self._logger_tree():
            logger.__dict__["_log_cache"] = []

    def _logger_tree(self):
        """Return this logger and all nested sub-loggers, each once, in discovery order."""
        tree = []
        seen = set()
        pending = [self]
        while pending:
            logger = pending.pop()
            if id(logger) in seen:
                continue
            seen.add(id(logger))
            tree.append(logger)
            pending.extend(reversed(logger._sub_loggers()))
        return tree

    def _sub_loggers(self):
        sub_loggers = []
        for name, v in self.__dict__.items():
            if name in ("_log_row", "_log_cache"):
                continue
            if isinstance(v, LoggerMixin):
                sub_loggers.append(v)
            elif isinstance(v, (list, tuple)):
                sub_loggers.extend(c for c in v if isinstance(c, LoggerMixin))
        return sub_loggers
