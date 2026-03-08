from __future__ import annotations

import time
from typing import Any, Iterable

import requests

TILE_TO_INT: dict[str, int] = {
    **{f"{i}m": i - 1 for i in range(1, 10)},
    **{f"{i}p": i + 8 for i in range(1, 10)},
    **{f"{i}s": i + 17 for i in range(1, 10)},
    **{f"{i}z": i + 26 for i in range(1, 8)},
    "0m": 34,
    "0p": 35,
    "0s": 36,
}

INT_TO_TILE: dict[int, str] = {value: key for key, value in TILE_TO_INT.items()}
INT_TO_TILE[-1] = "DRAW_STATE"

MELD_TYPE_TO_INT: dict[Any, int] = {
    0: 0,
    1: 1,
    2: 2,
    3: 3,
    4: 4,
    "pong": 0,
    "pon": 0,
    "碰": 0,
    "chow": 1,
    "chi": 1,
    "吃": 1,
    "closed_kong": 2,
    "ankan": 2,
    "暗杠": 2,
    "暗槓": 2,
    "open_kong": 3,
    "daiminkan": 3,
    "明杠": 3,
    "明槓": 3,
    "added_kong": 4,
    "kakan": 4,
    "加杠": 4,
    "加槓": 4,
}


def encode_tile(tile: str | int) -> int:
    if isinstance(tile, int):
        if -1 <= tile <= 36:
            return tile
        raise ValueError(f"tile int out of range: {tile}")
    if tile not in TILE_TO_INT:
        raise ValueError(f"unknown tile string: {tile}")
    return TILE_TO_INT[tile]


def decode_tile(tile: int) -> str:
    return INT_TO_TILE.get(tile, f"UNKNOWN({tile})")


def encode_tiles(tiles: Iterable[str | int]) -> list[int]:
    return [encode_tile(tile) for tile in tiles]


def normalize_meld(meld: dict[str, Any]) -> dict[str, Any]:
    meld_type = MELD_TYPE_TO_INT.get(meld["type"])
    if meld_type is None:
        raise ValueError(f"unknown meld type: {meld['type']}")
    return {
        "type": meld_type,
        "tiles": encode_tiles(meld["tiles"]),
    }


def build_request(
    *,
    hand: Iterable[str | int],
    melds: Iterable[dict[str, Any]],
    dora_indicators: Iterable[str | int],
    round_wind: str | int,
    seat_wind: str | int,
    wall: list[int] | None = None,
    version: str = "0.9.1",
    enable_reddora: bool = True,
    enable_uradora: bool = True,
    enable_shanten_down: bool = True,
    enable_tegawari: bool = True,
    enable_riichi: bool = True,
    ip: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "enable_reddora": enable_reddora,
        "enable_uradora": enable_uradora,
        "enable_shanten_down": enable_shanten_down,
        "enable_tegawari": enable_tegawari,
        "enable_riichi": enable_riichi,
        "round_wind": encode_tile(round_wind),
        "dora_indicators": encode_tiles(dora_indicators),
        "hand": encode_tiles(hand),
        "melds": [normalize_meld(meld) for meld in melds],
        "seat_wind": encode_tile(seat_wind),
        "version": version,
    }
    if wall is not None:
        if len(wall) != 37:
            raise ValueError(f"wall must have 37 counts, got {len(wall)}")
        payload["wall"] = wall
    if ip:
        payload["ip"] = ip
    return payload


def request_recommendation(
    payload: dict[str, Any],
    *,
    server_url: str = "http://127.0.0.1:50000",
    timeout: float = 15.0,
) -> dict[str, Any]:
    last_error = None
    for attempt in range(2):
        try:
            response = requests.post(
                server_url,
                json=payload,
                timeout=timeout,
                headers={"Connection": "close"},
            )
            response.raise_for_status()
            data = response.json()
            if not data.get("success"):
                raise RuntimeError(data.get("err_msg", "unknown mahjong-cpp error"))
            return data
        except (requests.RequestException, RuntimeError) as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(0.15)
                continue
            raise
    raise last_error


def rank_stats(
    result: dict[str, Any],
    *,
    turn: int = 1,
    limit: int = 3,
) -> list[dict[str, Any]]:
    response = result.get("response", result)
    stats = response.get("stats", [])
    config = response.get("config") or {}
    calc_stats = bool(config.get("calc_stats", False))
    ranked: list[dict[str, Any]] = []
    for stat in stats:
        necessary_tiles = stat.get("necessary_tiles", [])
        exp_score = _pick_turn_value(stat.get("exp_score", []), turn) if calc_stats else None
        win_prob = _pick_turn_value(stat.get("win_prob", []), turn) if calc_stats else None
        tenpai_prob = _pick_turn_value(stat.get("tenpai_prob", []), turn) if calc_stats else None
        ranked.append(
            {
                "tile": stat["tile"],
                "tile_str": decode_tile(stat["tile"]),
                "shanten": stat["shanten"],
                "necessary_tiles": necessary_tiles,
                "necessary_tiles_text": " ".join(
                    f"{decode_tile(item['tile'])}({item['count']})" for item in necessary_tiles
                ) or "-",
                "necessary_total": sum(item["count"] for item in necessary_tiles),
                "necessary_types": len(necessary_tiles),
                "calc_stats": calc_stats,
                "exp_score": exp_score,
                "win_prob": win_prob,
                "tenpai_prob": tenpai_prob,
            }
        )
    ranked.sort(
        key=lambda item: (
            -int(item["shanten"]),
            float(item["exp_score"] if item["exp_score"] is not None else float("-inf")),
            float(item["win_prob"] if item["win_prob"] is not None else float("-inf")),
            item["necessary_total"],
        ),
        reverse=True,
    )
    return ranked[:limit]


def _pick_turn_value(values: list[float], turn: int) -> float:
    if not values:
        return 0.0
    if turn < 0:
        return 0.0
    if turn >= len(values):
        return float(values[-1])
    return float(values[turn])

