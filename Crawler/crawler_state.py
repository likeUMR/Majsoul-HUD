from crawler_utils import TILE_DISPLAY_ORDER, classify_fulu, remove_tile_once, tile_sort_key


class RoundStateTracker:
    def __init__(self):
        self.self_seat = None
        self.in_round = False
        self.round_chang = 0
        self.round_ju = 0
        self.turn_index = 0
        self.tedashi_counts = [0, 0, 0, 0]
        self.visible_counts = {tile: 0 for tile in TILE_DISPLAY_ORDER}
        self.hands = {seat: [] for seat in range(4)}
        self.melds = {seat: [] for seat in range(4)}
        self.pending_self_hand = []
        self.dora_indicators = []
        self.last_discard_tile = None
        self.last_discard_seat = None
        self.algo_current_eval = None
        self.algo_recommended_action = None
        self.algo_recommended_eval = None
        self.self_tingpais = None

    def _bind_self_seat(self, new_self_seat):
        if not isinstance(new_self_seat, int):
            return
        if new_self_seat == self.self_seat:
            return

        if self.pending_self_hand and not self.hands.get(new_self_seat):
            self.hands[new_self_seat] = list(self.pending_self_hand)
            self.pending_self_hand = []
        elif isinstance(self.self_seat, int) and self.self_seat != new_self_seat:
            if self.hands.get(self.self_seat) and not self.hands.get(new_self_seat):
                self.hands[new_self_seat] = list(self.hands[self.self_seat])
                self.hands[self.self_seat] = []
            if self.melds.get(self.self_seat) and not self.melds.get(new_self_seat):
                self.melds[new_self_seat] = list(self.melds[self.self_seat])
                self.melds[self.self_seat] = []

        self.self_seat = new_self_seat

    def _update_self_seat_from_action(self, action_data):
        operation = action_data.get("operation")
        if isinstance(operation, dict):
            op_seat = operation.get("seat")
            if isinstance(op_seat, int):
                self._bind_self_seat(op_seat)
                return

    def _has_self_discard_option(self, action_data):
        operation = action_data.get("operation")
        if not isinstance(operation, dict):
            return False
        operation_list = operation.get("operation_list") or []
        return any(op.get("type") == 1 for op in operation_list)

    def _update_doras(self, doras):
        if doras:
            self.dora_indicators = list(doras)

    def _action_doras(self, action_data):
        return action_data.get("doras") or ([action_data["dora"]] if action_data.get("dora") else [])

    def reset_round(self, seat, hand, doras, chang=0, ju=0):
        self.self_seat = seat if isinstance(seat, int) else None
        self.in_round = True
        self.round_chang = chang if isinstance(chang, int) else 0
        self.round_ju = ju if isinstance(ju, int) else 0
        self.turn_index = 0
        self.tedashi_counts = [0, 0, 0, 0]
        self.visible_counts = {tile: 0 for tile in TILE_DISPLAY_ORDER}
        self.hands = {seat_id: [] for seat_id in range(4)}
        self.melds = {seat_id: [] for seat_id in range(4)}
        self.pending_self_hand = list(hand or [])
        self.dora_indicators = list(doras or [])
        self.last_discard_tile = None
        self.last_discard_seat = None
        self.algo_current_eval = None
        self.algo_recommended_action = None
        self.algo_recommended_eval = None
        self.self_tingpais = None
        if self.self_seat is not None:
            self.hands[self.self_seat] = list(self.pending_self_hand)
            self.pending_self_hand = []
        self._mark_tiles(hand or [])
        self._mark_tiles(doras or [])

    def set_algo_current_eval(self, ranked_item):
        if not ranked_item:
            self.algo_current_eval = None
            return
        self.algo_current_eval = self._compact_algo_eval(ranked_item)

    def set_algo_recommended_eval(self, ranked_item):
        if not ranked_item:
            self.algo_recommended_eval = None
            return
        self.algo_recommended_eval = self._compact_algo_eval(ranked_item)

    def _compact_algo_eval(self, ranked_item):
        return {
            "tile_str": ranked_item.get("tile_str"),
            "shanten": ranked_item.get("shanten"),
            "exp_score": ranked_item.get("exp_score"),
            "win_prob": ranked_item.get("win_prob"),
            "tenpai_prob": ranked_item.get("tenpai_prob"),
            "necessary_tiles_text": ranked_item.get("necessary_tiles_text") or "-",
            "necessary_total": ranked_item.get("necessary_total"),
            "necessary_types": ranked_item.get("necessary_types"),
        }

    def set_algo_recommended_action(self, action_text):
        self.algo_recommended_action = action_text or None

    def set_self_tingpais(self, tingpais_summary):
        self.self_tingpais = dict(tingpais_summary or {}) if tingpais_summary else None

    def _mark_tile(self, tile, amount=1):
        if not tile:
            return
        if tile not in self.visible_counts:
            self.visible_counts[tile] = 0
        self.visible_counts[tile] += amount

    def _mark_tiles(self, tiles):
        for tile in tiles or []:
            self._mark_tile(tile)

    def _append_meld(self, seat, tiles, meld_type=None):
        self.melds.setdefault(seat, []).append(
            {
                "tiles": list(tiles or []),
                "type": meld_type or "",
            }
        )

    def _upgrade_kakan(self, seat, tile):
        meld_list = self.melds.setdefault(seat, [])
        normalized = "5" + tile[1] if tile.startswith("0") else tile
        for meld in meld_list:
            meld_tiles = meld.get("tiles", [])
            if len(meld_tiles) == 3:
                normalized_tiles = [("5" + t[1]) if t.startswith("0") else t for t in meld_tiles]
                if len(set(normalized_tiles)) == 1 and normalized_tiles[0] == normalized:
                    meld_tiles.append(tile)
                    meld["type"] = "加杠"
                    return
        self._append_meld(seat, [tile], "加杠")

    def update_new_round(self, action_data):
        self.reset_round(
            None,
            action_data.get("tiles") or [],
            self._action_doras(action_data),
            action_data.get("chang", 0),
            action_data.get("ju", 0),
        )
        self._update_self_seat_from_action(action_data)
        # In dealer opening turns Majsoul may omit operation.seat even though
        # the payload already says "self can discard". In that case self must be dealer.
        if self.self_seat is None and self._has_self_discard_option(action_data):
            self._bind_self_seat(self.round_ju)

    def update_deal(self, action_data):
        self._update_self_seat_from_action(action_data)
        seat = action_data.get("seat", 0)
        tile = action_data.get("tile")
        # When the server sends an actual drawn tile, that tile is only visible to self.
        if self.self_seat is None and tile and isinstance(seat, int):
            self._bind_self_seat(seat)
        if seat == self.self_seat and tile:
            self.hands[self.self_seat].append(tile)
            self.hands[self.self_seat].sort(key=tile_sort_key)
            self._mark_tile(tile)
            self.turn_index += 1
        doras = self._action_doras(action_data)
        self._update_doras(doras)
        self._mark_tiles(doras)

    def update_discard(self, action_data):
        self._update_self_seat_from_action(action_data)
        seat = action_data.get("seat", 0)
        tile = action_data.get("tile") or action_data.get("pai")
        self.last_discard_tile = tile
        self.last_discard_seat = seat
        if not action_data.get("moqie"):
            self.tedashi_counts[seat] += 1

        if seat == self.self_seat and tile:
            remove_tile_once(self.hands[self.self_seat], tile)
            self.algo_recommended_action = None
            self.algo_recommended_eval = None
        elif tile:
            self._mark_tile(tile)

        doras = self._action_doras(action_data)
        self._update_doras(doras)
        self._mark_tiles(doras)

    def update_chi_peng_gang(self, action_data):
        self._update_self_seat_from_action(action_data)
        seat = action_data.get("seat", 0)
        tiles = list(action_data.get("tiles") or [])
        froms = list(action_data.get("froms") or [])
        self._append_meld(seat, tiles, classify_fulu(tiles, action_data.get("type")))

        if seat == self.self_seat:
            for index, tile in enumerate(tiles):
                if index < len(froms) and froms[index] == seat:
                    remove_tile_once(self.hands[self.self_seat], tile)
        else:
            for index, tile in enumerate(tiles):
                if index < len(froms) and froms[index] == seat:
                    self._mark_tile(tile)
        self.last_discard_tile = None
        self.last_discard_seat = None

    def update_angang_addgang(self, action_data):
        self._update_self_seat_from_action(action_data)
        seat = action_data.get("seat", 0)
        tile = action_data.get("tiles") or action_data.get("tile")
        gang_type = action_data.get("type")
        if not tile:
            return

        if gang_type == 3:
            self._upgrade_kakan(seat, tile)
            if seat == self.self_seat:
                remove_tile_once(self.hands[self.self_seat], tile)
            else:
                self._mark_tile(tile)
        else:
            self._append_meld(seat, [tile] * 4, "暗杠")
            if seat == self.self_seat:
                for _ in range(4):
                    remove_tile_once(self.hands[self.self_seat], tile)
            else:
                self._mark_tile(tile, 4)

        doras = self._action_doras(action_data)
        self._update_doras(doras)
        self._mark_tiles(doras)

    def update_babei(self, action_data):
        self._update_self_seat_from_action(action_data)
        seat = action_data.get("seat", 0)
        self._append_meld(seat, ["4z"], "拔北")
        if seat == self.self_seat:
            remove_tile_once(self.hands[self.self_seat], "4z")
        else:
            self._mark_tile("4z")
        doras = self._action_doras(action_data)
        self._update_doras(doras)
        self._mark_tiles(doras)

    def snapshot_for_algo(self):
        self_hand = list(self.pending_self_hand)
        self_melds_source = []
        if isinstance(self.self_seat, int):
            self_hand = list(self.hands.get(self.self_seat, []))
            self_melds_source = self.melds.get(self.self_seat, [])
        return {
            "self_seat": self.self_seat,
            "round_chang": self.round_chang,
            "round_ju": self.round_ju,
            "self_hand": self_hand,
            "self_melds": [
                {
                    "tiles": list(meld.get("tiles", [])),
                    "type": meld.get("type", ""),
                }
                for meld in self_melds_source
            ],
            "visible_counts": {tile: self.visible_counts.get(tile, 0) for tile in TILE_DISPLAY_ORDER},
            "dora_indicators": list(self.dora_indicators),
            "last_discard_tile": self.last_discard_tile,
            "last_discard_seat": self.last_discard_seat,
        }

    def as_payload(self):
        snapshot = self.snapshot_for_algo()
        return {
            "tedashi_counts": list(self.tedashi_counts),
            "turn_index": self.turn_index,
            "self_seat": snapshot["self_seat"],
            "self_hand": snapshot["self_hand"],
            "self_melds": snapshot["self_melds"],
            "visible_counts": snapshot["visible_counts"],
            "algo_current_eval": dict(self.algo_current_eval or {}),
            "algo_recommended_action": self.algo_recommended_action or "",
            "algo_recommended_eval": dict(self.algo_recommended_eval or {}),
            "self_tingpais": dict(self.self_tingpais or {}),
        }
