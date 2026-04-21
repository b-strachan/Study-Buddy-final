#!/usr/bin/env python3
"""Build a Moodle-installable ZIP for the local floating_ai plugin.

This script:
1) Reads the plugin component from version.php.
2) Stages files into a temp folder named exactly as the component.
3) Creates <component>.zip with exactly one top-level directory.

Run from repository root:
    python build_moodle_zip.py
"""

from __future__ import annotations

import argparse
import re
import shutil
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


COMPONENT_PATTERN = re.compile(r"\$plugin->component\s*=\s*'([^']+)'")

# Exclude dev/build/cache noise and raw source assets not needed for Moodle install.
EXCLUDED_DIR_NAMES = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "node_modules",
}

EXCLUDED_FILE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".psd",
    ".ai",
    ".sketch",
    ".fig",
    ".map",
}

EXCLUDED_RELATIVE_DIRS = {
    Path("amd/src"),
}


def parse_component(version_file: Path) -> str:
    text = version_file.read_text(encoding="utf-8")
    match = COMPONENT_PATTERN.search(text)
    if not match:
        raise ValueError(f"Could not find $plugin->component in {version_file}")
    return match.group(1)


def find_plugin_version_file(project_root: Path) -> Path:
    candidates = sorted(project_root.glob("local/*/version.php"))
    component_files = []

    for candidate in candidates:
        try:
            parse_component(candidate)
            component_files.append(candidate)
        except ValueError:
            continue

    if not component_files:
        raise FileNotFoundError("No local plugin version.php with $plugin->component found.")

    if len(component_files) > 1:
        files = "\n".join(str(p) for p in component_files)
        raise RuntimeError(
            "Found multiple local plugin version.php files. Please keep one or extend the script to choose one:\n"
            f"{files}"
        )

    return component_files[0]


def plugin_source_dir_from_component(project_root: Path, component: str) -> Path:
    if "_" not in component:
        raise ValueError(f"Unexpected component format: {component}")

    plugin_type, plugin_name = component.split("_", 1)
    path_from_type = project_root / plugin_type / plugin_name
    if path_from_type.exists():
        return path_from_type

    # Fallback if repo already uses the full component name as a directory.
    component_dir = project_root / component
    if component_dir.exists():
        return component_dir

    raise FileNotFoundError(
        f"Could not resolve plugin source directory from component '{component}'. "
        f"Tried '{path_from_type}' and '{component_dir}'."
    )


def is_excluded_dir(rel_dir: Path) -> bool:
    if not rel_dir.parts:
        return False
    if any(part in EXCLUDED_DIR_NAMES for part in rel_dir.parts):
        return True
    if rel_dir in EXCLUDED_RELATIVE_DIRS:
        return True
    return False


def should_copy_file(rel_file: Path) -> bool:
    if any(part in EXCLUDED_DIR_NAMES for part in rel_file.parts):
        return False
    if rel_file.suffix.lower() in EXCLUDED_FILE_SUFFIXES:
        return False
    for excluded_rel in EXCLUDED_RELATIVE_DIRS:
        try:
            rel_file.relative_to(excluded_rel)
            return False
        except ValueError:
            continue
    return True


def stage_plugin_files(source_dir: Path, staging_component_dir: Path) -> int:
    copied_count = 0

    for src_path in source_dir.rglob("*"):
        rel = src_path.relative_to(source_dir)

        if src_path.is_dir():
            if is_excluded_dir(rel):
                continue
            continue

        if not should_copy_file(rel):
            continue

        dst_path = staging_component_dir / rel
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dst_path)
        copied_count += 1

    return copied_count


def create_zip_from_staging(staging_root: Path, component: str, output_zip: Path) -> None:
    if output_zip.exists():
        output_zip.unlink()

    with ZipFile(output_zip, "w", compression=ZIP_DEFLATED) as zf:
        component_dir = staging_root / component
        for path in sorted(component_dir.rglob("*")):
            if path.is_dir():
                continue
            arcname = path.relative_to(staging_root).as_posix()
            zf.write(path, arcname=arcname)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Moodle plugin zip package.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Project root directory (default: current working directory).",
    )
    args = parser.parse_args()

    project_root = args.root.resolve()
    version_file = find_plugin_version_file(project_root)
    component = parse_component(version_file)
    source_dir = plugin_source_dir_from_component(project_root, component)

    with tempfile.TemporaryDirectory(prefix="moodle_build_") as temp_dir:
        temp_root = Path(temp_dir)
        staging_component_dir = temp_root / component
        staging_component_dir.mkdir(parents=True, exist_ok=True)

        copied = stage_plugin_files(source_dir, staging_component_dir)
        if copied == 0:
            raise RuntimeError("No files were copied into staging; zip would be empty.")

        output_zip = project_root / f"{component}.zip"
        create_zip_from_staging(temp_root, component, output_zip)

    print(f"Component: {component}")
    print(f"Source:    {source_dir}")
    print(f"Files:     {copied}")
    print(f"Output:    {output_zip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())