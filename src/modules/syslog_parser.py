"""
Syslog parser module.
Reads local syslog files, matches against incident patterns, and returns detected incidents.
"""

import re
import os
import time
import logging
from datetime import datetime
from typing import Any

log = logging.getLogger("agent.logparser")


def _tail_file(filepath: str, lines: int = 500) -> list:
    """
    Read the last N lines of a file efficiently.
    Falls back to reading the whole file if the file is small.
    """
    if not os.path.exists(filepath):
        log.warning("Log file not found: %s", filepath)
        return []

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()

        if len(all_lines) > lines:
            all_lines = all_lines[-lines:]

        return [line.rstrip("\n") for line in all_lines]
    except PermissionError:
        log.error("Permission denied reading: %s", filepath)
        return []
    except Exception as e:
        log.error("Error reading %s: %s", filepath, e)
        return []


def parse_syslog(config: Any) -> list:
    """
    Read and parse syslog files according to config.

    Args:
        config: Config object with syslog section containing:
            log_files: list of file paths
            tail_lines: number of lines to read
            patterns: list of {name, regex, severity} dicts

    Returns:
        List of incident dicts:
            {timestamp_raw, source_file, pattern_name, severity, matched_line, line_number}
    """
    syslog_cfg = config.get("syslog")
    if not syslog_cfg:
        log.warning("No syslog configuration found")
        return []

    log_files = syslog_cfg.get("log_files", [])
    tail_lines = syslog_cfg.get("tail_lines", 500)
    patterns = syslog_cfg.get("patterns", [])

    if not log_files:
        log.warning("No log files configured")
        return []

    if not patterns:
        log.warning("No incident patterns configured")
        return []

    # Compile regex patterns
    compiled = []
    for p in patterns:
        try:
            compiled.append({
                "name": p.get("name", "unnamed"),
                "regex": re.compile(p.get("regex", ""), re.IGNORECASE),
                "severity": p.get("severity", "warning"),
            })
        except re.error as e:
            log.error("Invalid regex for pattern '%s': %s", p.get("name"), e)

    log.info("Parsing %d log file(s) with %d pattern(s)", len(log_files), len(compiled))

    incidents = []

    for filepath in log_files:
        log.info("Reading: %s (last %d lines)", filepath, tail_lines)
        lines = _tail_file(filepath, tail_lines)

        for line_num, line in enumerate(lines, start=1):
            for pat in compiled:
                match = pat["regex"].search(line)
                if match:
                    # Extract timestamp from syslog line if possible
                    ts_raw = _extract_timestamp(line)

                    incidents.append({
                        "timestamp_raw": ts_raw,
                        "source_file": filepath,
                        "pattern_name": pat["name"],
                        "severity": pat["severity"],
                        "matched_line": line.strip()[:300],  # truncate long lines
                        "line_number": line_num,
                    })

    log.info("Detected %d incident(s) from log parsing", len(incidents))
    return incidents


def _extract_timestamp(line: str) -> str:
    """
    Try to extract a timestamp from the beginning of a syslog line.
    Common formats:
        Oct 23 10:15:30 hostname ...
        2026-10-23T10:15:30+07:00 hostname ...
        2026-10-23 10:15:30 ...
    """
    # ISO format: 2026-10-23T10:15:30
    m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+\-]\d{2}:\d{2})", line)
    if m:
        return m.group(1)

    # Date-time format: 2026-10-23 10:15:30
    m = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
    if m:
        return m.group(1)

    # Syslog format: Oct 23 10:15:30
    m = re.match(r"^([A-Z][a-z]{2}\s+\d{1,2}\s\d{2}:\d{2}:\d{2})", line)
    if m:
        return m.group(1)

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def summarize_incidents(incidents: list) -> dict:
    """
    Create a summary of incidents grouped by severity and pattern name.

    Returns:
        {
            "total": int,
            "by_severity": {"critical": N, "error": N, "warning": N},
            "by_pattern": {"pattern_name": N, ...},
            "top_incidents": [list of first 10 critical incidents]
        }
    """
    summary = {
        "total": len(incidents),
        "by_severity": {},
        "by_pattern": {},
        "top_incidents": [],
    }

    for inc in incidents:
        sev = inc["severity"]
        name = inc["pattern_name"]

        summary["by_severity"][sev] = summary["by_severity"].get(sev, 0) + 1
        summary["by_pattern"][name] = summary["by_pattern"].get(name, 0) + 1

    # Get top critical incidents (limit to 10)
    critical = [i for i in incidents if i["severity"] == "critical"]
    summary["top_incidents"] = critical[:10]

    return summary
