import argparse
import atexit
import datetime as dt
import msvcrt
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALGO_DIR = PROJECT_ROOT / "Algorithm" / "mahjong-cpp-master"
SERVER_DIR = ALGO_DIR / "build-ucrt-app" / "src" / "server"
SERVER_EXE = SERVER_DIR / "nanikiru.exe"
STATE_DIR = PROJECT_ROOT / ".runtime"
LOCK_PATH = STATE_DIR / "algorithm_backend.lock"
PID_PATH = STATE_DIR / "algorithm_backend.pid"
LOG_PATH = STATE_DIR / "algorithm_backend_launcher.log"
REQUIRED_DLLS = [
    "libspdlog-1.17.dll",
    "libgcc_s_seh-1.dll",
    "libwinpthread-1.dll",
    "libstdc++-6.dll",
]
MSYS_UCRT_BIN = Path(r"C:\msys64\ucrt64\bin")
MSYS_USR_BIN = Path(r"C:\msys64\usr\bin")

_stop_event = threading.Event()
_lock_handle = None


def ensure_state_dir():
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def timestamp():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(message):
    ensure_state_dir()
    line = f"[{timestamp()}] {message}"
    print(line, flush=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def port_open(host, port, timeout=0.25):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def ensure_runtime():
    missing = []
    for path in (SERVER_EXE, SERVER_DIR / "request_schema.json", SERVER_DIR / "uradora.bin"):
        if not path.exists():
            missing.append(str(path))
    if missing:
        raise FileNotFoundError("Missing runtime files:\n" + "\n".join(missing))
    missing_dlls = []
    for dll_name in REQUIRED_DLLS:
        if not (SERVER_DIR / dll_name).exists() and not (MSYS_UCRT_BIN / dll_name).exists():
            missing_dlls.append(dll_name)
    if missing_dlls:
        raise FileNotFoundError(
            "Missing runtime DLLs:\n"
            + "\n".join(missing_dlls)
            + "\nExpected them beside nanikiru.exe or under "
            + str(MSYS_UCRT_BIN)
        )


def build_env():
    env = os.environ.copy()
    extra_paths = [str(SERVER_DIR)]
    for path in (MSYS_UCRT_BIN, MSYS_USR_BIN):
        if path.exists():
            extra_paths.append(str(path))
    existing = env.get("PATH", "")
    env["PATH"] = os.pathsep.join(extra_paths + ([existing] if existing else []))
    return env


def acquire_lock():
    global _lock_handle
    ensure_state_dir()
    LOCK_PATH.touch(exist_ok=True)
    handle = LOCK_PATH.open("r+b")
    try:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.seek(0)
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        handle.close()
        return False
    _lock_handle = handle
    return True


def release_lock():
    global _lock_handle
    if _lock_handle is None:
        return
    try:
        _lock_handle.seek(0)
        msvcrt.locking(_lock_handle.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        pass
    try:
        _lock_handle.close()
    except OSError:
        pass
    _lock_handle = None


def write_pid():
    ensure_state_dir()
    PID_PATH.write_text(str(os.getpid()), encoding="ascii")


def clear_pid():
    try:
        PID_PATH.unlink()
    except FileNotFoundError:
        pass


def install_signal_handlers():
    def _handle_stop(signum, _frame):
        log(f"Launcher received signal {signum}, stopping...")
        _stop_event.set()

    for sig_name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        sig = getattr(signal, sig_name, None)
        if sig is not None:
            signal.signal(sig, _handle_stop)


def start_child(port):
    env = build_env()
    creationflags = 0
    creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        [str(SERVER_EXE), str(port)],
        cwd=str(SERVER_DIR),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    log(f"Started nanikiru.exe pid={process.pid} port={port}")
    return process


def stop_child(process, reason):
    if process is None:
        return
    if process.poll() is not None:
        return
    log(f"Stopping nanikiru.exe pid={process.pid} ({reason})")
    try:
        process.terminate()
        process.wait(timeout=5)
    except Exception:
        try:
            process.kill()
            process.wait(timeout=5)
        except Exception:
            pass


def wait_until_ready(port, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not _stop_event.is_set():
        if port_open("127.0.0.1", port, timeout=0.3):
            return True
        time.sleep(0.2)
    return False


def serve_forever(port):
    ensure_runtime()
    if port_open("127.0.0.1", port, timeout=0.25):
        log(f"Port {port} is already in use, launcher will not start another backend.")
        return 0
    if not acquire_lock():
        log("Another algorithm launcher instance is already active.")
        return 0

    write_pid()
    atexit.register(clear_pid)
    atexit.register(release_lock)
    install_signal_handlers()
    log(f"Launcher online. server_dir={SERVER_DIR}")

    restart_backoff = 1.0
    consecutive_failures = 0
    child = None
    exit_code = 0
    try:
        while not _stop_event.is_set():
            child = start_child(port)
            if wait_until_ready(port, timeout=15.0):
                consecutive_failures = 0
                restart_backoff = 1.0
                log(f"Backend is ready on 127.0.0.1:{port}")
            else:
                code = child.poll()
                log(f"Backend did not become ready within timeout. exit_code={code}")
                consecutive_failures += 1
                stop_child(child, "startup timeout")
                child = None
                if consecutive_failures >= 3:
                    exit_code = 1
                    break
                time.sleep(restart_backoff)
                restart_backoff = min(restart_backoff * 2.0, 8.0)
                continue

            while not _stop_event.is_set():
                code = child.poll()
                if code is not None:
                    log(f"Backend exited unexpectedly. pid={child.pid} exit_code={code}")
                    child = None
                    consecutive_failures += 1
                    break
                time.sleep(0.5)

            if _stop_event.is_set():
                break

            if consecutive_failures >= 5:
                log("Backend crashed too many times, launcher is giving up.")
                exit_code = 1
                break

            log(f"Restarting backend after {restart_backoff:.1f}s backoff.")
            time.sleep(restart_backoff)
            restart_backoff = min(restart_backoff * 2.0, 8.0)
    finally:
        stop_child(child, "launcher shutdown")
        clear_pid()
        release_lock()
        log(f"Launcher exiting with code {exit_code}")
    return exit_code


def build_parser():
    parser = argparse.ArgumentParser(description="Stable supervisor for mahjong-cpp backend.")
    parser.add_argument("command", nargs="?", default="serve", choices=["serve"])
    parser.add_argument("--port", type=int, default=50000, help="TCP port for nanikiru.exe")
    return parser


def main():
    args = build_parser().parse_args()
    try:
        if args.command == "serve":
            return serve_forever(args.port)
        return 1
    except Exception as exc:
        log(f"Launcher fatal error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
