import os
import socket
import subprocess
import sys
import time

from crawler_runtime import compact_json, logger
from crawler_utils import remove_tile_once, tile_to_display_text
from mahjong_cpp_client import build_request, rank_stats, request_recommendation


ALGO_ENABLED = os.environ.get("MAJSOUL_ALGO", "1").strip().lower() not in {"0", "false", "off", "no"}
ALGO_SERVER_HOST = os.environ.get("MAJSOUL_ALGO_HOST", "127.0.0.1")
ALGO_SERVER_PORT = int(os.environ.get("MAJSOUL_ALGO_PORT", "50000"))
ALGO_SERVER_URL = os.environ.get("MAJSOUL_ALGO_URL", f"http://{ALGO_SERVER_HOST}:{ALGO_SERVER_PORT}")
ALGO_VERSION = os.environ.get("MAJSOUL_ALGO_VERSION", "0.9.1")
ALGO_TIMEOUT = float(os.environ.get("MAJSOUL_ALGO_TIMEOUT", "4.0"))
ALGO_TURN_INDEX = int(os.environ.get("MAJSOUL_ALGO_TURN", "1"))
ALGO_TOPK = int(os.environ.get("MAJSOUL_ALGO_TOPK", "3"))
ALGO_MIN_EXP_RATIO = float(os.environ.get("MAJSOUL_ALGO_MIN_EXP_RATIO", "0.1"))
ALGO_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ALGO_PROJECT_ROOT = os.path.dirname(ALGO_BASE_DIR)
ALGO_LAUNCHER = os.path.join(ALGO_PROJECT_ROOT, "tools", "launchers", "algorithm_backend_launcher.py")

OP_CHI = 2
OP_PENG = 3
OP_DAMINGGANG = 4
OP_ANGANG = 5
OP_JIAGANG = 6

WIND_TILES = ["1z", "2z", "3z", "4z"]
BASE_FIVE_INDEX = {34: 4, 35: 13, 36: 22}


def _wind_tile(index):
    if isinstance(index, int) and 0 <= index < 4:
        return WIND_TILES[index]
    return "1z"


def _build_wall(visible_counts):
    wall = [4] * 34 + [1, 1, 1]
    tile_to_index = {
        **{f"{i}m": i - 1 for i in range(1, 10)},
        **{f"{i}p": i + 8 for i in range(1, 10)},
        **{f"{i}s": i + 17 for i in range(1, 10)},
        **{f"{i}z": i + 26 for i in range(1, 8)},
        "0m": 34,
        "0p": 35,
        "0s": 36,
    }
    for tile, count in (visible_counts or {}).items():
        index = tile_to_index.get(tile)
        if index is None:
            continue
        used = int(count or 0)
        wall[index] = max(0, wall[index] - used)
        # mahjong-cpp internally still treats red fives as part of the base 5-tile pool,
        # so a visible red five must also consume one slot from the corresponding normal 5.
        if tile in {"0m", "0p", "0s"}:
            base_five = "5" + tile[1]
            base_index = tile_to_index[base_five]
            wall[base_index] = max(0, wall[base_index] - used)
    return wall


def _request_payload(snapshot, hand=None, melds=None):
    self_seat = snapshot.get("self_seat")
    round_ju = snapshot.get("round_ju", 0)
    seat_wind = _wind_tile(((self_seat - round_ju + 4) % 4) if isinstance(self_seat, int) else 0)
    return build_request(
        hand=hand if hand is not None else snapshot.get("self_hand") or [],
        melds=melds if melds is not None else snapshot.get("self_melds") or [],
        dora_indicators=snapshot.get("dora_indicators") or [],
        round_wind=_wind_tile(snapshot.get("round_chang", 0)),
        seat_wind=seat_wind,
        wall=_build_wall(snapshot.get("visible_counts") or {}),
        version=ALGO_VERSION,
    )


def _used_counts_for_payload(payload):
    used = [0] * 37
    for tile in payload.get("hand") or []:
        used[tile] += 1
        if tile in BASE_FIVE_INDEX:
            used[BASE_FIVE_INDEX[tile]] += 1
    for tile in payload.get("dora_indicators") or []:
        used[tile] += 1
        if tile in BASE_FIVE_INDEX:
            used[BASE_FIVE_INDEX[tile]] += 1
    for meld in payload.get("melds") or []:
        for tile in meld.get("tiles") or []:
            used[tile] += 1
            if tile in BASE_FIVE_INDEX:
                used[BASE_FIVE_INDEX[tile]] += 1
    return used


def _validate_wall_payload(payload):
    wall = payload.get("wall")
    if wall is None:
        return []

    errors = []
    if len(wall) != 37:
        return [f"wall length invalid: {len(wall)}"]

    used = _used_counts_for_payload(payload)
    for index, count in enumerate(wall):
        if count < 0:
            errors.append(f"wall[{index}] is negative: {count}")

    for index in range(34):
        if used[index] + wall[index] > 4:
            errors.append(f"tile {index} exceeds limit: used={used[index]}, wall={wall[index]}, max=4")
    for index in range(34, 37):
        if used[index] + wall[index] > 1:
            errors.append(f"red tile {index} exceeds limit: used={used[index]}, wall={wall[index]}, max=1")

    return errors


def _parse_combo(combo):
    if isinstance(combo, str):
        return [tile for tile in combo.split("|") if tile]
    return list(combo or [])


def _normalized_tile(tile):
    if isinstance(tile, str) and tile.startswith("0"):
        return "5" + tile[1]
    return tile


def _remove_tiles(tiles, consumed):
    result = list(tiles or [])
    for tile in consumed:
        if not remove_tile_once(result, tile):
            return None
    return result


def _port_open(host="127.0.0.1", port=ALGO_SERVER_PORT, timeout=0.5):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _is_connection_issue(exc):
    text = repr(exc)
    return "10061" in text or "ConnectionRefusedError" in text or "Failed to establish a new connection" in text


def _branch_tiles_for_call(op_type, combo_tiles, last_discard_tile):
    if op_type in {OP_ANGANG, OP_JIAGANG}:
        return list(combo_tiles)

    if not last_discard_tile:
        return list(combo_tiles)

    if len(combo_tiles) <= 2:
        return list(combo_tiles)

    consumed = list(combo_tiles)
    normalized_last = _normalized_tile(last_discard_tile)
    for index, tile in enumerate(consumed):
        if _normalized_tile(tile) == normalized_last:
            consumed.pop(index)
            return consumed
    return consumed[:-1]


def _upgrade_added_kong(melds, combo_tiles):
    updated = [dict(meld) for meld in melds]
    if not combo_tiles:
        return updated
    target = _normalized_tile(combo_tiles[0])
    for meld in updated:
        meld_tiles = list(meld.get("tiles") or [])
        normalized = [_normalized_tile(tile) for tile in meld_tiles]
        if meld.get("type") == "碰" and len(normalized) == 3 and len(set(normalized)) == 1 and normalized[0] == target:
            meld["type"] = "加杠"
            meld["tiles"] = list(combo_tiles)
            return updated
    updated.append({"type": "加杠", "tiles": list(combo_tiles)})
    return updated


def simulate_operation_branch(snapshot, op_type, combo_tiles):
    hand = list(snapshot.get("self_hand") or [])
    melds = [dict(meld) for meld in snapshot.get("self_melds") or []]
    last_discard_tile = snapshot.get("last_discard_tile")
    consumed_tiles = _branch_tiles_for_call(op_type, combo_tiles, last_discard_tile)

    if op_type == OP_CHI:
        next_hand = _remove_tiles(hand, consumed_tiles)
        if next_hand is None:
            return None
        melds.append({"type": "吃", "tiles": list(combo_tiles)})
        return {"hand": next_hand, "melds": melds}

    if op_type == OP_PENG:
        next_hand = _remove_tiles(hand, consumed_tiles)
        if next_hand is None:
            return None
        melds.append({"type": "碰", "tiles": list(combo_tiles)})
        return {"hand": next_hand, "melds": melds}

    if op_type == OP_DAMINGGANG:
        next_hand = _remove_tiles(hand, consumed_tiles)
        if next_hand is None:
            return None
        melds.append({"type": "明杠", "tiles": list(combo_tiles)})
        return {"hand": next_hand, "melds": melds}

    if op_type == OP_ANGANG:
        next_hand = _remove_tiles(hand, consumed_tiles)
        if next_hand is None:
            return None
        melds.append({"type": "暗杠", "tiles": list(combo_tiles)})
        return {"hand": next_hand, "melds": melds}

    if op_type == OP_JIAGANG:
        next_hand = _remove_tiles(hand, consumed_tiles)
        if next_hand is None:
            return None
        return {"hand": next_hand, "melds": _upgrade_added_kong(melds, combo_tiles)}

    return None


def format_rank_line(prefix, ranked_item):
    exp_score = ranked_item.get("exp_score")
    win_prob = ranked_item.get("win_prob")
    tenpai_prob = ranked_item.get("tenpai_prob")
    exp_score_text = "-" if exp_score is None else f"{exp_score:.1f}"
    win_prob_text = "-" if win_prob is None else f"{win_prob:.3f}"
    tenpai_prob_text = "-" if tenpai_prob is None else f"{tenpai_prob:.3f}"
    return (
        f"{prefix}推荐切 {ranked_item['tile_str']} | 向听 {ranked_item['shanten']} | "
        f"有效 {ranked_item['necessary_total']}张/{ranked_item['necessary_types']}种 | "
        f"第{ALGO_TURN_INDEX}巡期待 {exp_score_text} | "
        f"和率 {win_prob_text} | 听率 {tenpai_prob_text}"
    )


def compare_key(ranked_item):
    return (
        -int(ranked_item.get("shanten", 99)),
        float(ranked_item.get("exp_score") if ranked_item.get("exp_score") is not None else float("-inf")),
        float(ranked_item.get("win_prob") if ranked_item.get("win_prob") is not None else float("-inf")),
        int(ranked_item.get("necessary_total", 0)),
    )


def _exp_guard_baseline(baseline_item):
    if not baseline_item:
        return None
    exp_score = baseline_item.get("exp_score")
    if exp_score is None:
        return None
    exp_score = float(exp_score)
    return exp_score if exp_score > 0 else None


def _exp_guard_rejected(ranked_item, baseline_exp):
    if baseline_exp is None:
        return False
    exp_score = ranked_item.get("exp_score")
    if exp_score is None:
        return False
    return float(exp_score) <= (baseline_exp * ALGO_MIN_EXP_RATIO)


class MahjongRecommender:
    def __init__(self):
        self.enabled = ALGO_ENABLED
        self.last_error_message = ""
        self.last_error_at = 0.0
        self.last_turn_best = None
        self.last_turn_candidates = {}
        self.last_restart_attempt_at = 0.0

    def reset_round_cache(self):
        self.last_turn_best = None
        self.last_turn_candidates = {}

    def _throttled_error(self, emit, message):
        now = time.monotonic()
        if message != self.last_error_message or (now - self.last_error_at) >= 10.0:
            emit(message)
            self.last_error_message = message
            self.last_error_at = now

    def _restart_algo_server_if_needed(self):
        now = time.monotonic()
        if (now - self.last_restart_attempt_at) < 5.0:
            return False
        self.last_restart_attempt_at = now

        if _port_open():
            return True
        if not os.path.exists(ALGO_LAUNCHER):
            logger.warning("Algorithm restart skipped, launcher not found: %s", ALGO_LAUNCHER)
            return False

        try:
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.Popen(
                [sys.executable, ALGO_LAUNCHER, "serve", "--port", str(ALGO_SERVER_PORT)],
                cwd=ALGO_PROJECT_ROOT,
                creationflags=creationflags,
            )
        except OSError as exc:
            logger.warning("Algorithm restart failed to launch: %r", exc)
            return False

        for _ in range(40):
            if _port_open(timeout=0.3):
                logger.warning("Algorithm server restarted successfully via %s", ALGO_LAUNCHER)
                return True
            time.sleep(0.2)
        logger.warning("Algorithm restart attempted but port %s is still unavailable", ALGO_SERVER_PORT)
        return False

    def _call(self, payload, limit=ALGO_TOPK):
        started = time.perf_counter()
        last_error = None
        payload_candidates = []

        wall_errors = _validate_wall_payload(payload)
        if wall_errors:
            logger.warning(
                "Algorithm payload wall validation failed: %s payload=%s",
                "; ".join(wall_errors),
                compact_json(payload),
            )
            fallback_payload = dict(payload)
            fallback_payload.pop("wall", None)
            payload_candidates.append(("without_wall_after_validation_failure", fallback_payload))
        else:
            payload_candidates.append(("with_wall", payload))
            if "wall" in payload:
                fallback_payload = dict(payload)
                fallback_payload.pop("wall", None)
                payload_candidates.append(("without_wall_fallback", fallback_payload))

        restarted = False
        while True:
            for mode, candidate in payload_candidates:
                try:
                    result = request_recommendation(candidate, server_url=ALGO_SERVER_URL, timeout=ALGO_TIMEOUT)
                    elapsed_ms = (time.perf_counter() - started) * 1000.0
                    response = result.get("response") or {}
                    algo_time_ms = float(response.get("time", 0)) / 1000.0
                    ranked = rank_stats(result, turn=ALGO_TURN_INDEX, limit=limit)
                    if mode != "with_wall":
                        logger.warning("Algorithm request succeeded via fallback mode=%s payload=%s", mode, compact_json(candidate))
                    return result, ranked, elapsed_ms, algo_time_ms
                except Exception as exc:
                    last_error = exc
                    logger.warning(
                        "Algorithm request failed mode=%s error=%s payload=%s",
                        mode,
                        repr(exc),
                        compact_json(candidate),
                    )
                    continue

            if (not restarted) and last_error and _is_connection_issue(last_error) and self._restart_algo_server_if_needed():
                restarted = True
                continue
            break

        raise last_error

    def _candidate_lookup_key(self, tile):
        normalized = _normalized_tile(tile)
        if isinstance(tile, str) and tile.startswith("5"):
            return "0" + tile[1]
        return normalized

    def resolve_actual_discard(self, tile):
        if not tile:
            return None
        exact = self.last_turn_candidates.get(tile)
        if exact:
            return dict(exact)
        normalized = self.last_turn_candidates.get(_normalized_tile(tile))
        if normalized:
            return dict(normalized)
        alternate = self.last_turn_candidates.get(self._candidate_lookup_key(tile))
        if alternate:
            return dict(alternate)
        return None

    def _op_name(self, op_type):
        return {
            OP_CHI: "吃",
            OP_PENG: "碰",
            OP_DAMINGGANG: "明杠",
            OP_ANGANG: "暗杠",
            OP_JIAGANG: "加杠",
        }.get(op_type, "操作")

    def format_action_text(self, action_name, tiles=None):
        if action_name == "过":
            return "过"
        tiles = tiles or []
        if action_name == "打" and tiles:
            return tile_to_display_text(tiles[0])
        if not tiles:
            return action_name
        return f"{action_name} {' '.join(tile_to_display_text(tile) for tile in tiles)}"

    def emit_turn_recommendation(self, snapshot, baseline_item, emit):
        if not self.enabled:
            return None
        if snapshot.get("self_seat") is None or not snapshot.get("self_hand"):
            return None
        try:
            payload = _request_payload(snapshot)
            result, all_ranked, elapsed_ms, algo_time_ms = self._call(payload, limit=128)
        except Exception as exc:
            self._throttled_error(emit, f"[算法] 当前可打推荐失败: {exc}")
            return None

        response = result.get("response") or {}
        emit(
            f"[算法] 当前可打推荐: 算法{algo_time_ms:.1f}ms, 总耗时{elapsed_ms:.1f}ms, "
            f"搜索{response.get('searched', '?')}"
        )
        if not all_ranked:
            self.last_turn_best = None
            self.last_turn_candidates = {}
            emit("  - 当前未返回可用的切牌结果")
            return None
        baseline_exp = _exp_guard_baseline(baseline_item)
        filtered_ranked = []
        rejected_count = 0
        for item in all_ranked:
            if _exp_guard_rejected(item, baseline_exp):
                rejected_count += 1
                continue
            filtered_ranked.append(item)
        if not filtered_ranked:
            filtered_ranked = list(all_ranked)
        ranked = filtered_ranked[:ALGO_TOPK]
        if rejected_count and baseline_exp is not None:
            emit(
                f"  - 已忽略 {rejected_count} 个垃圾候选"
                f" (期待值 <= 当前牌效的 {ALGO_MIN_EXP_RATIO:.0%}, 基准 {baseline_exp:.1f})"
            )
        self.last_turn_best = {
            "snapshot": snapshot,
            "best": dict(filtered_ranked[0]),
            "algo_time_ms": algo_time_ms,
            "elapsed_ms": elapsed_ms,
            "searched": response.get("searched", "?"),
        }
        self.last_turn_candidates = {}
        for item in all_ranked:
            self.last_turn_candidates[item.get("tile_str")] = dict(item)
            self.last_turn_candidates[_normalized_tile(item.get("tile_str"))] = dict(item)
        for index, item in enumerate(ranked, start=1):
            emit(f"  - {index}. {format_rank_line('', item)}")
        return {
            "ranked": ranked,
            "best": dict(filtered_ranked[0]),
            "algo_time_ms": algo_time_ms,
            "elapsed_ms": elapsed_ms,
            "searched": response.get("searched", "?"),
        }

    def emit_operation_recommendations(self, snapshot, operation, baseline_item, emit):
        if not self.enabled:
            return None
        if snapshot.get("self_seat") is None or not snapshot.get("self_hand"):
            return None
        if not isinstance(operation, dict):
            return None
        op_seat = operation.get("seat")
        if op_seat is not None and op_seat != snapshot.get("self_seat"):
            return None

        operation_list = operation.get("operation_list") or []
        branch_ops = [op for op in operation_list if op.get("type") in {OP_CHI, OP_PENG, OP_DAMINGGANG, OP_ANGANG, OP_JIAGANG}]
        if not branch_ops:
            return None

        emit("[算法] 吃碰杠机会评估:")
        if baseline_item:
            emit(f"  - 不鸣基准(当前实际): {format_rank_line('', baseline_item)}")
        else:
            emit("  - 不鸣基准: -")

        best_action_text = None
        best_branch_item = None

        for op in branch_ops:
            combos = op.get("combination") or []
            if not combos:
                combos = [op.get("change_tiles") or []]
            for combo in combos:
                combo_tiles = _parse_combo(combo)
                branch = simulate_operation_branch(snapshot, op.get("type"), combo_tiles)
                branch_name = self.format_action_text(self._op_name(op.get("type")), combo_tiles)
                if not branch:
                    emit(f"  - 操作 {branch_name} -> 无法根据当前手牌模拟")
                    continue
                try:
                    payload = _request_payload(snapshot, hand=branch["hand"], melds=branch["melds"])
                    _, ranked, elapsed_ms, algo_time_ms = self._call(payload)
                    if ranked:
                        compare_text = ""
                        guard_rejected = False
                        if baseline_item:
                            baseline_exp = _exp_guard_baseline(baseline_item)
                            guard_rejected = _exp_guard_rejected(ranked[0], baseline_exp)
                            better = (not guard_rejected) and (compare_key(ranked[0]) > compare_key(baseline_item))
                            if guard_rejected:
                                compare_text = (
                                    f" | 期待值跌破基准{ALGO_MIN_EXP_RATIO:.0%}"
                                    f"(基准 {baseline_exp:.1f})，忽略"
                                )
                            else:
                                compare_text = " | 优于不鸣" if better else " | 不优于不鸣"
                        else:
                            better = True
                        if better and (best_branch_item is None or compare_key(ranked[0]) > compare_key(best_branch_item)):
                            best_branch_item = dict(ranked[0])
                            best_action_text = branch_name
                        emit(
                            f"  - {branch_name} -> {format_rank_line('', ranked[0])} | "
                            f"算法{algo_time_ms:.1f}ms/总{elapsed_ms:.1f}ms{compare_text}"
                        )
                    else:
                        emit(f"  - {branch_name} -> 未返回可用切牌结果 | 算法{algo_time_ms:.1f}ms/总{elapsed_ms:.1f}ms")
                except Exception as exc:
                    self._throttled_error(emit, f"[算法] 分支 {branch_name} 计算失败: {exc}")
        if baseline_item and best_action_text is None:
            best_action_text = "过"
        return {
            "recommended_action": best_action_text,
            "best_branch": best_branch_item,
        }
