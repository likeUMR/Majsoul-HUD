LOGIN_METHODS = {
    ".lq.Lobby.login",
    ".lq.Lobby.fetchInfo",
    ".lq.Lobby.fetchAccountInfo",
    ".lq.Lobby.loginSuccess",
    ".lq.Lobby.oauth2Auth",
}

SESSION_METHODS = {
    ".lq.FastTest.authGame",
    ".lq.FastTest.enterGame",
    ".lq.FastTest.syncGame",
    ".lq.NotifyRoomGameStart",
    ".lq.NotifyMatchGameStart",
}

OPERATION_NAMES = {
    1: "出牌",
    2: "吃",
    3: "碰",
    4: "大明杠",
    5: "暗杠",
    6: "加杠",
    7: "立直",
    8: "自摸/和牌",
    9: "荣和",
    10: "九种九牌",
    11: "拔北",
}

FULU_TYPE_NAMES = {
    0: "吃/碰/杠",
    1: "碰",
    2: "吃",
    3: "大明杠",
}

LIUJU_TYPE_NAMES = {
    1: "九种九牌",
    2: "四风连打",
    3: "四杠散了",
    4: "四家立直",
    5: "三家和了",
}

TILE_DISPLAY_ORDER = [
    "0m", "1m", "2m", "3m", "4m", "5m", "6m", "7m", "8m", "9m",
    "0p", "1p", "2p", "3p", "4p", "5p", "6p", "7p", "8p", "9p",
    "0s", "1s", "2s", "3s", "4s", "5s", "6s", "7s", "8s", "9s",
    "1z", "2z", "3z", "4z", "5z", "6z", "7z",
]

NUMBER_TILE_TEXT = {
    "0": "赤五",
    "1": "一",
    "2": "二",
    "3": "三",
    "4": "四",
    "5": "五",
    "6": "六",
    "7": "七",
    "8": "八",
    "9": "九",
}
SUIT_TILE_TEXT = {
    "m": "万",
    "p": "筒",
    "s": "索",
}
HONOR_TILE_TEXT = {
    "1z": "东",
    "2z": "南",
    "3z": "西",
    "4z": "北",
    "5z": "白",
    "6z": "发",
    "7z": "中",
}


def seat_text(seat):
    if seat is None:
        return "?"
    return str(seat)


def seat_label(seat, self_if_missing=False):
    if seat is None:
        return "自家" if self_if_missing else "Seat ?"
    return f"Seat {seat}"


def tile_sort_key(tile):
    if not isinstance(tile, str) or len(tile) < 2:
        return ("?", 99)
    base = 5 if tile.startswith("0") else int(tile[0])
    return tile[1], base


def remove_tile_once(tiles, target):
    if target in tiles:
        tiles.remove(target)
        return True
    if isinstance(target, str) and target.startswith("0"):
        alt = "5" + target[1]
        if alt in tiles:
            tiles.remove(alt)
            return True
    if isinstance(target, str) and target.startswith("5"):
        alt = "0" + target[1]
        if alt in tiles:
            tiles.remove(alt)
            return True
    return False


def tile_group_text(combo):
    if isinstance(combo, str):
        tiles = combo.split("|")
    else:
        tiles = list(combo or [])
    if not tiles:
        return "-"
    return " ".join(tiles)


def tile_to_display_text(tile):
    if not isinstance(tile, str) or len(tile) < 2:
        return str(tile)
    if tile in HONOR_TILE_TEXT:
        return HONOR_TILE_TEXT[tile]
    num = NUMBER_TILE_TEXT.get(tile[0], tile[0])
    suit = SUIT_TILE_TEXT.get(tile[1], tile[1])
    return f"{num}{suit}"


def list_text(values):
    if not values:
        return "-"
    return " ".join(str(value) for value in values)


def fans_text(fans):
    if not fans:
        return "-"
    chunks = []
    for fan in fans:
        name = fan.get("name") or f"id={fan.get('id', '?')}"
        val = fan.get("val")
        if val is None:
            chunks.append(str(name))
        else:
            chunks.append(f"{name}x{val}")
    return ", ".join(chunks)


def response_ok(data):
    if not isinstance(data, dict):
        return True
    error = data.get("error")
    if not isinstance(error, dict):
        return True
    return error.get("code", 0) == 0


def extract_account_brief(data):
    if not isinstance(data, dict):
        return None
    account = data.get("account")
    if not isinstance(account, dict):
        return None
    account_id = account.get("account_id") or data.get("account_id")
    nickname = account.get("nickname") or "-"
    return f"{nickname} ({account_id})"


def classify_fulu(tiles, action_type=None):
    if action_type in FULU_TYPE_NAMES:
        return FULU_TYPE_NAMES[action_type]
    if not tiles:
        return "吃/碰/杠"
    if len(tiles) == 4:
        return "明杠"

    normalized = [("5" + tile[1]) if tile.startswith("0") else tile for tile in tiles]
    if len(set(normalized)) == 1:
        return "碰"

    suits = {tile[1] for tile in normalized}
    if len(tiles) == 3 and len(suits) == 1 and next(iter(suits)) in {"m", "p", "s"}:
        nums = sorted(int(tile[0]) for tile in normalized)
        if nums[0] + 1 == nums[1] and nums[1] + 1 == nums[2]:
            return "吃"
    return "吃/碰/杠"


def tingpais_lines(tingpais, prefix):
    if not tingpais:
        return []

    rendered = []
    for item in tingpais:
        tile = item.get("tile", "?")
        count = item.get("count")
        yi = item.get("haveyi")
        chunk = tile
        if count is not None:
            chunk += f"(余{count})"
        if yi is not None:
            chunk += ",有役" if yi else ",无役"
        rendered.append(chunk)
    return [f"  - {prefix}: {', '.join(rendered)}"]


def summarize_tingpais(tingpais):
    if not tingpais:
        return None

    rendered = []
    total = 0
    for item in tingpais:
        tile = item.get("tile", "?")
        count = item.get("count")
        yi = item.get("haveyi")
        chunk = tile
        if count is not None:
            total += int(count)
            chunk += f"(余{count})"
        if yi is not None:
            chunk += ",有役" if yi else ",无役"
        rendered.append(chunk)

    return {
        "text": ", ".join(rendered),
        "total": total,
        "types": len(tingpais),
    }


def operation_lines(operation, self_if_missing=False):
    if not isinstance(operation, dict):
        return []

    seat = operation.get("seat")
    ops = operation.get("operation_list") or []
    if not ops:
        return []

    lines = []
    for op in ops:
        op_type = op.get("type")
        name = OPERATION_NAMES.get(op_type, f"操作{op_type}")
        combos = op.get("combination") or []
        change_tiles = op.get("change_tiles") or []
        extras = []

        if combos:
            extras.append("组合: " + " / ".join(tile_group_text(combo) for combo in combos))
        if change_tiles:
            extras.append("变更牌: " + list_text(change_tiles))

        if extras:
            lines.append(f"  - {seat_label(seat, self_if_missing)} 可选{name}: {'; '.join(extras)}")
        else:
            lines.append(f"  - {seat_label(seat, self_if_missing)} 可选{name}")
    return lines
