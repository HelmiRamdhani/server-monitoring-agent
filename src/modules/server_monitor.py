"""
Server monitoring module.
Collects system metrics (CPU, memory, disk, uptime) using psutil.
Works on both Linux and Windows.
"""

import time
import platform
import logging
from typing import Any

import psutil

log = logging.getLogger("agent.monitor")


def _get_uptime() -> float:
    """Return system uptime in seconds."""
    if platform.system() == "Windows":
        import ctypes
        GetTickCount64 = ctypes.windll.kernel32.GetTickCount64
        GetTickCount64.restype = ctypes.c_uint64
        return GetTickCount64() / 1000.0
    else:
        with open("/proc/uptime", "r") as f:
            return float(f.readline().split()[0])


def _format_uptime(seconds: float) -> str:
    """Convert seconds to a human-readable string."""
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"{days}d {hours}h {minutes}m"


def collect_metrics() -> dict:
    """
    Collect current server metrics.

    Returns a dict with the following keys:
        timestamp, os, hostname, cpu_percent, cpu_count,
        memory_percent, memory_total_gb, memory_used_gb,
        disk_percent, disk_total_gb, disk_used_gb,
        uptime_seconds, uptime_human, load_avg
    """
    log.info("Collecting server metrics...")

    cpu_percent = psutil.cpu_percent(interval=2)
    cpu_count = psutil.cpu_count(logical=True)

    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/" if platform.system() != "Windows" else "C:\\")

    try:
        uptime_sec = _get_uptime()
        uptime_human = _format_uptime(uptime_sec)
    except Exception as e:
        log.warning("Could not read uptime: %s", e)
        uptime_sec = 0
        uptime_human = "unknown"

    # load average (Linux only, None on Windows)
    try:
        load_avg = list(psutil.getloadavg())
    except (AttributeError, OSError):
        load_avg = None

    metrics = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "os": platform.system(),
        "os_version": platform.version(),
        "hostname": platform.node(),
        "cpu_percent": round(cpu_percent, 1),
        "cpu_count": cpu_count,
        "memory_percent": round(mem.percent, 1),
        "memory_total_gb": round(mem.total / (1024**3), 2),
        "memory_used_gb": round(mem.used / (1024**3), 2),
        "disk_percent": round(disk.percent, 1),
        "disk_total_gb": round(disk.total / (1024**3), 2),
        "disk_used_gb": round(disk.used / (1024**3), 2),
        "uptime_seconds": round(uptime_sec, 0),
        "uptime_human": uptime_human,
        "load_avg": load_avg,
    }

    log.info(
        "Metrics: CPU %.1f%%, MEM %.1f%%, DISK %.1f%%, Uptime %s",
        metrics["cpu_percent"],
        metrics["memory_percent"],
        metrics["disk_percent"],
        metrics["uptime_human"],
    )

    return metrics


def check_thresholds(metrics: dict, thresholds: Any) -> list:
    """
    Compare metrics against thresholds and return a list of alerts.

    Args:
        metrics: dict from collect_metrics()
        thresholds: Config object with cpu_warning, cpu_critical, etc.

    Returns:
        List of alert dicts: {metric, value, threshold, severity, message}
    """
    alerts = []

    # Helper to check a metric
    def _check(metric_name: str, value: float, warn: float, crit: float, unit: str = "%"):
        if value >= crit:
            alerts.append({
                "metric": metric_name,
                "value": value,
                "threshold": crit,
                "severity": "critical",
                "message": f"{metric_name} {value}{unit} melampaui batas kritis ({crit}{unit})",
            })
        elif value >= warn:
            alerts.append({
                "metric": metric_name,
                "value": value,
                "threshold": warn,
                "severity": "warning",
                "message": f"{metric_name} {value}{unit} melampaui batas peringatan ({warn}{unit})",
            })

    _check("CPU", metrics["cpu_percent"], thresholds.cpu_warning, thresholds.cpu_critical)
    _check("Memory", metrics["memory_percent"], thresholds.memory_warning, thresholds.memory_critical)
    _check("Disk", metrics["disk_percent"], thresholds.disk_warning, thresholds.disk_critical)

    # Uptime check (recent reboot detection)
    uptime_min = getattr(thresholds, "uptime_min_seconds", 0)
    if uptime_min and metrics["uptime_seconds"] < uptime_min:
        alerts.append({
            "metric": "Uptime",
            "value": metrics["uptime_human"],
            "threshold": f"{uptime_min}s",
            "severity": "warning",
            "message": f"Server baru saja reboot (uptime: {metrics['uptime_human']})",
        })

    if alerts:
        log.warning("Found %d threshold alert(s)", len(alerts))
    else:
        log.info("All metrics within normal thresholds")

    return alerts
