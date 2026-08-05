"""Locate Microsoft Edge and read its Windows file version."""

import ctypes
import os
from ctypes import wintypes
from pathlib import Path


class _FixedFileInfo(ctypes.Structure):
    _fields_ = [
        ("signature", wintypes.DWORD),
        ("structure_version", wintypes.DWORD),
        ("file_version_ms", wintypes.DWORD),
        ("file_version_ls", wintypes.DWORD),
        ("product_version_ms", wintypes.DWORD),
        ("product_version_ls", wintypes.DWORD),
        ("file_flags_mask", wintypes.DWORD),
        ("file_flags", wintypes.DWORD),
        ("file_os", wintypes.DWORD),
        ("file_type", wintypes.DWORD),
        ("file_subtype", wintypes.DWORD),
        ("file_date_ms", wintypes.DWORD),
        ("file_date_ls", wintypes.DWORD),
    ]


def find_edge_executable() -> Path | None:
    roots = (
        os.environ.get("ProgramFiles(x86)"),
        os.environ.get("ProgramFiles"),
        os.environ.get("LOCALAPPDATA"),
    )
    for root in roots:
        if not root:
            continue
        executable = Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
        if executable.is_file():
            return executable.resolve()
    return None


def read_edge_major_version(executable: Path) -> int | None:
    if os.name != "nt":
        return None
    version = ctypes.windll.version
    size = version.GetFileVersionInfoSizeW(str(executable), None)
    if not size:
        return None
    buffer = ctypes.create_string_buffer(size)
    if not version.GetFileVersionInfoW(str(executable), 0, size, buffer):
        return None
    value = ctypes.c_void_p()
    value_length = wintypes.UINT()
    if not version.VerQueryValueW(
        buffer,
        "\\",
        ctypes.byref(value),
        ctypes.byref(value_length),
    ):
        return None
    info = ctypes.cast(value, ctypes.POINTER(_FixedFileInfo)).contents
    return info.file_version_ms >> 16
