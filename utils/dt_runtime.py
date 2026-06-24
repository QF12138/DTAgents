"""Helpers for loading DTGeoStudio's Python runtime on Windows."""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from types import ModuleType


_DLL_HANDLES: list[object] = []
_CONFIGURED = False


def _candidate_roots() -> list[Path]:
    roots: list[Path] = []
    for env_name in ("DTGEOSTUDIO_HOME", "DTGEOSTUDIO_ROOT", "DTGEO_HOME"):
        value = os.environ.get(env_name)
        if value:
            roots.append(Path(value))
    roots.append(Path("D:/DTGeoStudio"))
    roots.append(Path("C:/DTGeoStudio"))
    return roots


def configure_dt_runtime() -> Path | None:
    """Add DTGeoStudio scripts and DLL folders to this Python process."""
    global _CONFIGURED
    if _CONFIGURED:
        return next((root for root in _candidate_roots() if root.exists()), None)

    configured_root: Path | None = None
    seen: set[Path] = set()

    for root in _candidate_roots():
        root = root.resolve()
        if root in seen or not root.exists():
            continue
        seen.add(root)
        configured_root = configured_root or root

        scripts_dir = root / "scripts"
        if scripts_dir.exists():
            scripts_path = str(scripts_dir)
            if scripts_path not in sys.path:
                sys.path.insert(0, scripts_path)

        for dll_dir in (
            root,
            root / "install" / "bin",
            root / "vgedt" / "Library" / "bin",
        ):
            if dll_dir.exists():
                if hasattr(os, "add_dll_directory"):
                    _DLL_HANDLES.append(os.add_dll_directory(str(dll_dir)))
                path_value = str(dll_dir)
                path_parts = os.environ.get("PATH", "").split(os.pathsep)
                if path_value not in path_parts:
                    os.environ["PATH"] = path_value + os.pathsep + os.environ.get("PATH", "")

    _CONFIGURED = True
    return configured_root


def import_dt_runtime() -> ModuleType:
    """Configure paths and import DTPyRuntime."""
    configure_dt_runtime()
    return importlib.import_module("DTPyRuntime")
