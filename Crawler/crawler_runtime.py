import json
import logging
import os
import socket


LOG_FILE = os.path.abspath("crawler_debug.log")
TRACE_LOG = os.environ.get("MAJSOUL_TRACE_LOG", "").strip().lower() in {"1", "true", "yes", "on"}
HUD_ENABLED = os.environ.get("MAJSOUL_HUD", "1").strip().lower() not in {"0", "false", "off", "no"}
HUD_HOST = os.environ.get("MAJSOUL_HUD_HOST", "127.0.0.1")
HUD_PORT = int(os.environ.get("MAJSOUL_HUD_PORT", "44777"))
HUD_HEARTBEAT_INTERVAL = 1.0

logger = logging.getLogger("majsoul_crawler")
logger.setLevel(logging.DEBUG if TRACE_LOG else logging.INFO)
logger.propagate = False

if logger.hasHandlers():
    logger.handlers.clear()

file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8", mode="w")
file_handler.setLevel(logging.DEBUG if TRACE_LOG else logging.INFO)
file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(file_handler)

hud_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def compact_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def hud_send(message):
    if not HUD_ENABLED:
        return
    try:
        hud_socket.sendto(message.encode("utf-8", errors="replace"), (HUD_HOST, HUD_PORT))
    except OSError:
        pass


def hud_send_state(payload):
    if not HUD_ENABLED:
        return
    hud_send(json.dumps({"kind": "state", "payload": payload}, ensure_ascii=False))


def emit(message=""):
    print(message)
    hud_send(message)


def hud_clear():
    hud_send("__HUD_CLEAR__")
