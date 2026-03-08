import os
import threading
import time
from pprint import pformat

from mitmproxy import http

import liqi
from crawler_recommend import MahjongRecommender
from crawler_runtime import (
    HUD_ENABLED,
    HUD_HEARTBEAT_INTERVAL,
    LOG_FILE,
    TRACE_LOG,
    compact_json,
    emit,
    hud_clear,
    hud_send,
    hud_send_state,
    logger,
)
from crawler_state import RoundStateTracker
from crawler_utils import (
    LIUJU_TYPE_NAMES,
    LOGIN_METHODS,
    SESSION_METHODS,
    classify_fulu,
    extract_account_brief,
    fans_text,
    list_text,
    operation_lines,
    response_ok,
    seat_text,
    tile_sort_key,
    summarize_tingpais,
    tingpais_lines,
)

PROXY_HOST = os.environ.get("MAJSOUL_PROXY_HOST", "127.0.0.1")
PROXY_PORT = os.environ.get("MAJSOUL_PROXY_PORT", "8080")


class MajsoulListener:
    def __init__(self):
        self.game_recognized = False
        self.login_recognized = False
        self.heartbeat_running = False
        self.recommender = MahjongRecommender()
        self.state = RoundStateTracker()
        self.liqi = liqi.LiqiProto()

        if HUD_ENABLED:
            self.heartbeat_running = True
            threading.Thread(target=self._hud_heartbeat_loop, daemon=True).start()

        hud_clear()
        hud_send("[HUD] 监听器已连接")
        self.publish_state()
        emit(f"Majsoul CLI listener ready on proxy {PROXY_HOST}:{PROXY_PORT}")
        emit(f"Debug log: {LOG_FILE}")
        if TRACE_LOG:
            emit("Trace log: ON")
        emit("Waiting for login or game traffic...")
        logger.info("Listener initialized")

    def _hud_heartbeat_loop(self):
        while self.heartbeat_running:
            hud_send("__HUD_PING__")
            time.sleep(HUD_HEARTBEAT_INTERVAL)

    def done(self):
        self.heartbeat_running = False

    def publish_state(self):
        hud_send_state(self.state.as_payload())

    def _maybe_emit_turn_recommendation(self, action_data):
        operation = action_data.get("operation")
        if not isinstance(operation, dict):
            return
        op_seat = operation.get("seat")
        if op_seat is not None and op_seat != self.state.self_seat:
            return
        operation_list = operation.get("operation_list") or []
        if not any(op.get("type") == 1 for op in operation_list):
            return
        result = self.recommender.emit_turn_recommendation(
            self.state.snapshot_for_algo(),
            self.state.algo_current_eval,
            emit,
        )
        if result and result.get("best"):
            self.state.set_algo_recommended_action(
                self.recommender.format_action_text("打", [result["best"].get("tile_str", "?")])
            )
            self.state.set_algo_recommended_eval(result.get("best"))
        else:
            self.state.set_algo_recommended_action(None)
            self.state.set_algo_recommended_eval(None)

    def _maybe_emit_operation_recommendations(self, action_data):
        operation = action_data.get("operation")
        result = self.recommender.emit_operation_recommendations(
            self.state.snapshot_for_algo(),
            operation,
            self.state.algo_current_eval,
            emit,
        )
        # Preserve the normal discard recommendation in the HUD when there is
        # no actual chi/peng/gang branch to compare on this action.
        if result and result.get("recommended_action"):
            self.state.set_algo_recommended_action(result.get("recommended_action"))
            self.state.set_algo_recommended_eval(result.get("best_branch"))

    def websocket_message(self, flow: http.HTTPFlow):
        if "gateway" not in flow.request.path or not flow.websocket.messages:
            return

        message = flow.websocket.messages[-1]
        raw_content = getattr(message, "content", b"")
        if not raw_content:
            return

        try:
            result = self.liqi.parse(message)
        except Exception as exc:
            logger.exception("Parse error. from_client=%s raw_len=%s", message.from_client, len(raw_content))
            emit(f"[ParseError] {exc}，详情见 crawler_debug.log")
            return

        if not result:
            return

        method = result.get("method", "")
        data = result.get("data", {})
        if TRACE_LOG:
            logger.debug("Parsed method=%s from_client=%s data=%s", method, message.from_client, compact_json(data))

        if (not message.from_client) and (not self.login_recognized) and method in LOGIN_METHODS and response_ok(data):
            self.login_recognized = True
            account_brief = extract_account_brief(data)
            emit("")
            emit("=" * 60)
            emit(f"[登录成功] 已进入雀魂大厅: {account_brief}" if account_brief else "[登录成功] 已进入雀魂大厅")
            emit("=" * 60)
            logger.info("Login recognized via method=%s account=%s", method, account_brief)

        if (not message.from_client) and (not self.game_recognized) and method in SESSION_METHODS:
            self.game_recognized = True
            emit("")
            emit("=" * 60)
            emit("Majsoul game session detected")
            emit("=" * 60)
            logger.info("Game session recognized via method=%s", method)

        if method == ".lq.NotifyRoomGameStart":
            emit(f"[房间开局] uuid={data.get('game_uuid', '-')}, url={data.get('game_url', '-')}")
            return
        if method == ".lq.NotifyMatchGameStart":
            emit(f"[匹配开局] uuid={data.get('game_uuid', '-')}, mode={data.get('match_mode_id', '-')}")
            return
        if method == ".lq.ActionPrototype":
            self.print_action(data.get("name", ""), data.get("data", {}))
            return
        if method == ".lq.NotifyGameEndResult":
            emit(f"[对局结束] 收到结算通知: {compact_json(data)}")
            return
        if method == ".lq.NotifyGameTerminate":
            emit(f"[对局结束] 对局连接已关闭: {compact_json(data)}")

    def print_action(self, action_name, action_data):
        if TRACE_LOG:
            logger.info("Action %s: %s", action_name, compact_json(action_data))
        else:
            logger.info("Action %s", action_name)

        handler = getattr(self, f"_handle_{action_name}", None)
        if handler:
            handler(action_data)
            return

        emit(f"[未分类动作] {action_name}: {pformat(action_data, sort_dicts=False, width=120)}")
        self.publish_state()

    def _handle_ActionMJStart(self, action_data):
        emit("[麻将开始] 对局开始")
        self.publish_state()

    def _handle_ActionNewCard(self, action_data):
        emit(f"[新牌/新事件] {compact_json(action_data)}")

    def _handle_ActionNewRound(self, action_data):
        self.recommender.reset_round_cache()
        self.state.update_new_round(action_data)
        round_bits = []
        if action_data.get("chang") is not None:
            round_bits.append(f"场风={action_data.get('chang')}")
        if action_data.get("ju") is not None:
            round_bits.append(f"局数={action_data.get('ju')}")
        round_bits.append(f"本场={action_data.get('ben', 0)}")
        round_bits.append(f"立直棒={action_data.get('liqibang', 0)}")

        doras = action_data.get("doras") or ([action_data["dora"]] if action_data.get("dora") else [])
        emit("")
        emit("-" * 60)
        emit(f"[新局] {' '.join(round_bits)}")
        emit(f"  - 初始手牌: {list_text(action_data.get('tiles') or [])}")
        emit(f"  - 宝牌指示牌: {list_text(doras)}")
        emit(f"  - 当前分数: {action_data.get('scores') or '-'}")
        emit(f"  - 牌山剩余: {action_data.get('left_tile_count', '?')}")
        for line in operation_lines(action_data.get("operation"), self_if_missing=True):
            emit(line)
        self._maybe_emit_turn_recommendation(action_data)
        self._maybe_emit_operation_recommendations(action_data)
        self.publish_state()

    def _handle_ActionDealTile(self, action_data):
        self.state.update_deal(action_data)
        seat = action_data.get("seat", 0)
        tile = action_data.get("tile")
        left = action_data.get("left_tile_count", "?")
        emit(f"[摸牌] Seat {seat_text(seat)} {'摸到 ' + tile if tile else '摸牌'}, 牌山剩余 {left}")
        self._emit_common_action_details(action_data, seat, "听牌信息", self_if_missing=True)

    def _handle_ActionDiscardTile(self, action_data):
        self.state.update_discard(action_data)
        seat = action_data.get("seat", 0)
        tile = action_data.get("tile") or action_data.get("pai") or "?"
        if seat == self.state.self_seat:
            self.state.set_algo_current_eval(self.recommender.resolve_actual_discard(tile))
            self.state.set_algo_recommended_action(None)
            self.state.set_algo_recommended_eval(None)
        moqie = "摸切" if action_data.get("moqie") else "手切"
        emit(f"[出牌] Seat {seat_text(seat)} 打出 {tile} ({moqie})")
        if action_data.get("is_liqi"):
            emit(f"  - Seat {seat_text(seat)} 宣告立直")
        if action_data.get("is_wliqi"):
            emit(f"  - Seat {seat_text(seat)} 宣告双立直")
        self._emit_common_action_details(action_data, seat, "打后听牌")

    def _handle_ActionFillAwaitingTiles(self, action_data):
        emit(f"[补全待牌] 待牌: {list_text(action_data.get('awaiting_tiles'))}")
        emit(f"  - 牌山剩余: {action_data.get('left_tile_count', '?')}")
        if isinstance(action_data.get("liqi"), dict):
            emit(f"  - 立直信息: {compact_json(action_data.get('liqi'))}")
        for line in operation_lines(action_data.get("operation"), self_if_missing=True):
            emit(line)
        self._maybe_emit_turn_recommendation(action_data)
        self._maybe_emit_operation_recommendations(action_data)
        self.publish_state()

    def _handle_ActionChiPengGang(self, action_data):
        self.state.update_chi_peng_gang(action_data)
        seat = action_data.get("seat", 0)
        tiles = action_data.get("tiles") or []
        froms = action_data.get("froms") or []
        source = froms[-1] if froms else "?"
        shown_tiles = " ".join(sorted(tiles, key=tile_sort_key))
        fulu_name = classify_fulu(tiles, action_data.get("type"))
        emit(f"[副露] Seat {seat_text(seat)} {fulu_name}: {shown_tiles} <- Seat {seat_text(source)}")
        self._emit_common_action_details(action_data, seat, "副露后听牌")

    def _handle_ActionGangResult(self, action_data):
        emit(f"[杠结算] {compact_json(action_data)}")
        self.publish_state()

    def _handle_ActionGangResultEnd(self, action_data):
        emit(f"[杠结算结束] {compact_json(action_data)}")
        self.publish_state()

    def _handle_ActionAnGangAddGang(self, action_data):
        self.state.update_angang_addgang(action_data)
        seat = action_data.get("seat", 0)
        gang_type = action_data.get("type")
        if gang_type == 3:
            gang_name = "加杠"
        elif gang_type == 2:
            gang_name = "暗杠"
        else:
            gang_name = "暗杠/加杠"
        emit(f"[杠牌] Seat {seat_text(seat)} {gang_name}: {action_data.get('tiles') or action_data.get('tile') or '?'}")
        self._emit_common_action_details(action_data, seat, "杠后听牌")

    def _handle_ActionBaBei(self, action_data):
        self.state.update_babei(action_data)
        seat = action_data.get("seat", 0)
        moqie = "摸切" if action_data.get("moqie") else "非摸切"
        emit(f"[拔北] Seat {seat_text(seat)} ({moqie})")
        self._emit_common_action_details(action_data, seat, "拔北后听牌")

    def _handle_ActionHule(self, action_data):
        emit("[和牌] 本局结束")
        for hule in action_data.get("hules") or []:
            emit(f"  - Seat {seat_text(hule.get('seat'))} 和牌, 牌张 {hule.get('hu_tile', '?')}, 点数 {hule.get('point_sum') or hule.get('point_rong') or '?'}")
            emit(f"    手牌: {list_text(hule.get('hand') or [])}")
            emit(f"    副露: {list_text(hule.get('ming') or [])}")
            emit(f"    番型: {fans_text(hule.get('fans'))}")
        if action_data.get("delta_scores"):
            emit(f"  - 分数变动: {action_data.get('delta_scores')}")
        if action_data.get("scores"):
            emit(f"  - 结算后分数: {action_data.get('scores')}")
        self.publish_state()

    def _handle_ActionHuleXueZhanMid(self, action_data):
        emit("[和牌] 血战中途结算")
        for hule in action_data.get("hules") or []:
            emit(f"  - Seat {seat_text(hule.get('seat'))} 和牌, 牌张 {hule.get('hu_tile', '?')}, 番型: {fans_text(hule.get('fans'))}")
        if action_data.get("delta_scores"):
            emit(f"  - 分数变动: {action_data.get('delta_scores')}")
        self.publish_state()

    def _handle_ActionHuleXueZhanEnd(self, action_data):
        emit("[和牌] 血战最终结算")
        if action_data.get("delta_scores"):
            emit(f"  - 分数变动: {action_data.get('delta_scores')}")
        if action_data.get("scores"):
            emit(f"  - 结算后分数: {action_data.get('scores')}")
        self.publish_state()

    def _handle_ActionNoTile(self, action_data):
        players = action_data.get("players") or []
        tenpai_seats = [str(index) for index, player in enumerate(players) if player.get("tingpai")]
        emit("[流局] 荒牌流局")
        emit(f"  - 听牌玩家: {', '.join(tenpai_seats) if tenpai_seats else '-'}")
        for index, player in enumerate(players):
            if not player:
                continue
            if player.get("hand"):
                emit(f"  - Seat {index} 手牌: {list_text(player.get('hand'))}")
            for line in tingpais_lines(player.get("tings"), f"Seat {index} 听牌"):
                emit(line)
        for block in action_data.get("scores") or []:
            if block.get("delta_scores"):
                emit(f"  - 分数变动: {block.get('delta_scores')}")
        self.publish_state()

    def _handle_ActionLiuJu(self, action_data):
        liuju_name = LIUJU_TYPE_NAMES.get(action_data.get("type", "?"), f"type={action_data.get('type', '?')}")
        emit(f"[途中流局] {liuju_name}, seat={seat_text(action_data.get('seat'))}")
        if action_data.get("tiles"):
            emit(f"  - 相关牌: {list_text(action_data.get('tiles'))}")
        if action_data.get("allplayertiles"):
            emit(f"  - 所有玩家相关牌: {list_text(action_data.get('allplayertiles'))}")
        self.publish_state()

    def _handle_ActionSelectGap(self, action_data):
        self._emit_special(action_data, "ActionSelectGap")

    def _handle_ActionChangeTile(self, action_data):
        self._emit_special(action_data, "ActionChangeTile")

    def _handle_ActionRevealTile(self, action_data):
        self._emit_special(action_data, "ActionRevealTile")

    def _handle_ActionUnveilTile(self, action_data):
        self._emit_special(action_data, "ActionUnveilTile")

    def _handle_ActionLockTile(self, action_data):
        self._emit_special(action_data, "ActionLockTile")

    def _emit_common_action_details(self, action_data, seat, tingpai_label, self_if_missing=False):
        if seat == self.state.self_seat:
            self.state.set_self_tingpais(summarize_tingpais(action_data.get("tingpais")))
        if isinstance(action_data.get("liqi"), dict):
            liqi = action_data.get("liqi")
            emit(f"  - 立直成立: Seat {seat_text(seat)}, 分数 {liqi.get('score', '?')}, 立直棒 {liqi.get('liqibang', '?')}")
        if action_data.get("doras"):
            emit(f"  - 新宝牌指示牌: {list_text(action_data.get('doras'))}")
        if action_data.get("zhenting") is not None:
            emit(f"  - 振听: {action_data.get('zhenting')}")
        if action_data.get("scores"):
            emit(f"  - 当前分数: {action_data.get('scores')}")
        if action_data.get("liqibang") is not None:
            emit(f"  - 立直棒: {action_data.get('liqibang')}")
        for line in tingpais_lines(action_data.get("tingpais"), tingpai_label):
            emit(line)
        for line in operation_lines(action_data.get("operation"), self_if_missing=self_if_missing):
            emit(line)
        self._maybe_emit_turn_recommendation(action_data)
        self._maybe_emit_operation_recommendations(action_data)
        self.publish_state()

    def _emit_special(self, action_data, name):
        emit(f"[特殊动作] {name}: {compact_json(action_data)}")
        self.publish_state()
