from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path

PORTABLE_PYTHON_ROOT_FILES = [
    "python.exe",
    "pythonw.exe",
    "python311.dll",
    "python3.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll",
    "LICENSE.txt",
]
PORTABLE_PYTHON_DIRS = ["DLLs"]
PORTABLE_PYTHON_LIB_EXCLUDE_NAMES = [
    "__pycache__",
    "site-packages",
    "test",
    "ensurepip",
    "idlelib",
    "tkinter",
    "turtledemo",
    "venv",
]
PORTABLE_PYTHON_LIB_EXCLUDE_GLOBS = ["*.pyc", "*.pyo"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a portable AI_Mahjong release package.")
    parser.add_argument(
        "--manifest",
        default="tools/release_manifest.json",
        help="Relative path to the release manifest.",
    )
    parser.add_argument(
        "--name",
        default="",
        help="Optional exact output folder name. Defaults to prefix + timestamp.",
    )
    parser.add_argument(
        "--output-root",
        default="",
        help="Optional override for the output root directory.",
    )
    parser.add_argument(
        "--skip-zip",
        action="store_true",
        help="Skip creating the final zip archive.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be copied without writing files.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Delete an existing output directory with the same name.",
    )
    return parser.parse_args()


def load_manifest(root: Path, manifest_path: str) -> dict:
    path = root / manifest_path
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def should_skip_name(name: str, excluded_names: list[str]) -> bool:
    return name in excluded_names


def should_skip_file(rel_path: Path, excluded_globs: list[str]) -> bool:
    rel_posix = rel_path.as_posix()
    return any(fnmatch(rel_posix, pattern) or fnmatch(rel_path.name, pattern) for pattern in excluded_globs)


def copy_file(src: Path, dst: Path, dry_run: bool) -> int:
    print(f"[COPY] {src} -> {dst}")
    if not dry_run:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return 1


def copy_dir(
    src: Path,
    dst: Path,
    dry_run: bool,
    excluded_names: list[str],
    excluded_globs: list[str],
) -> int:
    copied = 0
    for item in src.rglob("*"):
        rel_path = item.relative_to(src)
        if any(should_skip_name(part, excluded_names) for part in rel_path.parts):
            continue
        if should_skip_file(rel_path, excluded_globs):
            continue
        if item.is_dir():
            continue
        copied += copy_file(item, dst / rel_path, dry_run)
    return copied


def copy_portable_python_runtime(dst: Path, dry_run: bool) -> int:
    base_python = Path(sys.base_prefix)
    if not base_python.exists():
        raise SystemExit(f"Portable Python source was not found: {base_python}")

    print(f"[INFO] Portable Python source: {base_python}")
    copied = 0
    for filename in PORTABLE_PYTHON_ROOT_FILES:
        source = base_python / filename
        if not source.exists():
            raise SystemExit(f"Missing Python runtime file: {source}")
        copied += copy_file(source, dst / filename, dry_run)

    for dirname in PORTABLE_PYTHON_DIRS:
        source = base_python / dirname
        if not source.exists():
            raise SystemExit(f"Missing Python runtime directory: {source}")
        copied += copy_dir(
            source,
            dst / dirname,
            dry_run,
            ["__pycache__"],
            PORTABLE_PYTHON_LIB_EXCLUDE_GLOBS,
        )

    lib_source = base_python / "Lib"
    if not lib_source.exists():
        raise SystemExit(f"Missing Python standard library directory: {lib_source}")
    copied += copy_dir(
        lib_source,
        dst / "Lib",
        dry_run,
        PORTABLE_PYTHON_LIB_EXCLUDE_NAMES,
        PORTABLE_PYTHON_LIB_EXCLUDE_GLOBS,
    )
    return copied


def validate_portable_runtime(release_dir: Path) -> None:
    runtime_dir = release_dir / "runtime" / "python"
    site_packages = release_dir / "runtime" / "site-packages"
    python_exe = runtime_dir / "python.exe"
    if not python_exe.exists() or not site_packages.exists():
        raise SystemExit("Portable runtime validation failed: missing runtime/python or runtime/site-packages.")

    env = os.environ.copy()
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    env["PYTHONHOME"] = str(runtime_dir)
    env["PYTHONPATH"] = str(site_packages)
    env["PYTHONNOUSERSITE"] = "1"

    result = subprocess.run(
        [
            str(python_exe),
            "-c",
            "import requests, mitmproxy, PIL; from mitmproxy.tools.main import mitmdump; print('portable-runtime-ok')",
        ],
        cwd=str(release_dir),
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(
            "Portable Python runtime validation failed.\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    print(f"[VALIDATE] {result.stdout.strip()}")


def validate_backend_runtime(release_dir: Path) -> None:
    server_dir = release_dir / "Algorithm" / "mahjong-cpp-master" / "build-ucrt-app" / "src" / "server"
    server_exe = server_dir / "nanikiru.exe"
    if not server_exe.exists():
        raise SystemExit(f"Backend runtime validation failed: missing {server_exe}")

    env = os.environ.copy()
    env["PATH"] = str(server_dir)
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        [str(server_exe), "59999"],
        cwd=str(server_dir),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    time.sleep(1.5)
    exit_code = process.poll()
    if exit_code is not None:
        raise SystemExit(
            "Backend runtime validation failed: nanikiru.exe exited immediately "
            f"with code {exit_code}."
        )
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    print("[VALIDATE] backend-runtime-ok")


def build_release(root: Path, args: argparse.Namespace) -> int:
    manifest = load_manifest(root, args.manifest)
    output_root = root / (args.output_root or manifest.get("output_root") or "dist")
    release_name = args.name or (
        f"{manifest.get('release_name_prefix', 'AI_Mahjong_Release')}_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    release_dir = output_root / release_name
    zip_enabled = bool(manifest.get("zip_release", True)) and not args.skip_zip
    excluded_names = list(manifest.get("global_exclude_names", []))
    excluded_globs = list(manifest.get("global_exclude_file_globs", []))

    print(f"[INFO] Project root: {root}")
    print(f"[INFO] Manifest: {root / args.manifest}")
    print(f"[INFO] Output dir: {release_dir}")
    print(f"[INFO] Dry run: {args.dry_run}")

    if release_dir.exists():
        if not args.overwrite:
            raise SystemExit(
                f"Output directory already exists: {release_dir}\n"
                "Use --name to choose another one, or pass --overwrite."
            )
        print(f"[INFO] Removing existing output directory: {release_dir}")
        if not args.dry_run:
            shutil.rmtree(release_dir)

    if not args.dry_run:
        release_dir.mkdir(parents=True, exist_ok=True)

    copied_files = 0
    for entry in manifest.get("copy_entries", []):
        target = release_dir / entry["target"]

        entry_excluded_names = excluded_names + list(entry.get("exclude_names", []))
        entry_excluded_globs = excluded_globs + list(entry.get("exclude_relative_globs", []))

        if entry["kind"] == "file":
            source = root / entry["source"]
            if not source.exists():
                raise SystemExit(f"Missing release input: {source}")
            copied_files += copy_file(source, target, args.dry_run)
        elif entry["kind"] == "dir":
            source = root / entry["source"]
            if not source.exists():
                raise SystemExit(f"Missing release input: {source}")
            copied_files += copy_dir(
                source,
                target,
                args.dry_run,
                entry_excluded_names,
                entry_excluded_globs,
            )
        elif entry["kind"] == "python_runtime":
            copied_files += copy_portable_python_runtime(target, args.dry_run)
        else:
            raise SystemExit(f"Unknown entry kind: {entry['kind']}")

    for entry in manifest.get("template_entries", []):
        source = root / entry["source"]
        target = release_dir / entry["target"]
        if not source.exists():
            raise SystemExit(f"Missing release template: {source}")
        copied_files += copy_file(source, target, args.dry_run)

    manifest_snapshot = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "release_name": release_name,
        "copied_files": copied_files,
        "source_root": str(root),
    }
    snapshot_path = release_dir / "release_build_info.json"
    print(f"[WRITE] {snapshot_path}")
    if not args.dry_run:
        snapshot_path.write_text(
            json.dumps(manifest_snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        validate_portable_runtime(release_dir)
        validate_backend_runtime(release_dir)

    if zip_enabled:
        zip_path = output_root / release_name
        print(f"[ZIP] {zip_path}.zip")
        if not args.dry_run:
            shutil.make_archive(str(zip_path), "zip", root_dir=output_root, base_dir=release_name)

    print(f"[DONE] Copied {copied_files} files into {release_dir}")
    return 0


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    args = parse_args()
    return build_release(root, args)


if __name__ == "__main__":
    raise SystemExit(main())
