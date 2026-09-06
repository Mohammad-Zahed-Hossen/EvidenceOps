"""Hardware resource monitoring and RAM tracking using standard library primitives."""

from __future__ import annotations

import ctypes
import os
import sys

from pydantic import BaseModel, ConfigDict


class ResourceSnapshot(BaseModel):
    """Snapshot of system memory and CPU utilization."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cpu_percent: float | None
    ram_used_mb: float | None
    ram_total_mb: float | None
    ram_percent: float | None


def _get_windows_memory() -> tuple[float | None, float | None, float | None]:
    """Retrieve physical RAM metrics on Windows via kernel32.GlobalMemoryStatusEx."""

    class MemoryStatusEx(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    stat = MemoryStatusEx()
    stat.dwLength = ctypes.sizeof(stat)
    try:
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return None, None, None
        total_mb = float(stat.ullTotalPhys / (1024 * 1024))
        avail_mb = float(stat.ullAvailPhys / (1024 * 1024))
        used_mb = total_mb - avail_mb
        percent = float(stat.dwMemoryLoad)
        return used_mb, total_mb, percent
    except Exception:
        return None, None, None


def _get_posix_memory() -> tuple[float | None, float | None, float | None]:
    """Retrieve physical RAM metrics on Linux/POSIX via /proc/meminfo or sysconf."""
    try:
        if os.path.exists("/proc/meminfo"):
            mem_info: dict[str, float] = {}
            with open("/proc/meminfo", encoding="utf-8") as f:
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        key = parts[0].strip()
                        val = float(parts[1].split()[0])  # in kB
                        mem_info[key] = val
            total_mb = mem_info["MemTotal"] / 1024
            avail_mb = mem_info["MemAvailable"] / 1024
            used_mb = total_mb - avail_mb
            percent = (used_mb / total_mb) * 100.0 if total_mb > 0 else 0.0
            return used_mb, total_mb, percent
    except Exception:
        pass
    return None, None, None


def get_current_resource_snapshot() -> ResourceSnapshot:
    """Capture current hardware resource metrics across operating systems
    without external packages.
    """
    if sys.platform == "win32":
        used_mb, total_mb, percent = _get_windows_memory()
    else:
        used_mb, total_mb, percent = _get_posix_memory()

    return ResourceSnapshot(
        cpu_percent=None,
        ram_used_mb=used_mb,
        ram_total_mb=total_mb,
        ram_percent=percent,
    )
