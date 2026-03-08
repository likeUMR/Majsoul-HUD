import argparse
import ctypes
import json
import os
import queue
import socket
import threading
import time
from ctypes import wintypes

from PIL import Image, ImageDraw, ImageFont


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HOST = "127.0.0.1"
PORT = 44777
HUD_LOG_FILE = os.path.join(BASE_DIR, "hud_debug.log")
BASE_SCREEN_WIDTH = 3840
BASE_SCREEN_HEIGHT = 2160
MAX_LOG_LINES = 18
BASE_LEFT = 8
BASE_TOP = 8
BASE_PADDING_X = 12
BASE_PADDING_Y = 8
BASE_LINE_SPACING = 2
TEXT_COLOR = (255, 220, 70, 255)
OUTLINE_COLOR = (0, 0, 0, 255)
STATE_LABEL_COLOR = (255, 220, 70, 255)
STATE_VALUE_COLOR = (120, 255, 220, 255)
STATE_SMALL_VALUE_COLOR = (140, 220, 255, 255)
BASE_FONT_SIZE = 18
BASE_SMALL_FONT_SIZE = 12
BASE_STATE_FONT_SIZE = 23
BASE_STATE_SMALL_FONT_SIZE = 16
BASE_ACTION_FONT_SIZE = 46
BASE_STROKE_WIDTH = 2
BASE_MIN_WIDTH = 180
HEARTBEAT_TIMEOUT_SECONDS = 3.0
REDRAW_INTERVAL_SECONDS = 0.08
CLASS_NAME = "MajsoulHudOverlayWindow"
HUD_EXTRA_SCALE_ENV = "MAJSOUL_HUD_EXTRA_SCALE"

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_TIMER = 0x0113
WM_NCHITTEST = 0x0084
HTTRANSPARENT = -1
WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008
WS_EX_NOACTIVATE = 0x08000000
ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
BI_RGB = 0
DIB_RGB_COLORS = 0
SW_SHOWNOACTIVATE = 4
SM_CXSCREEN = 0
SM_CYSCREEN = 1

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32
SYNCHRONIZE = 0x00100000
WAIT_OBJECT_0 = 0x00000000
LRESULT = getattr(wintypes, "LRESULT", ctypes.c_ssize_t)
UINT_PTR = getattr(wintypes, "UINT_PTR", ctypes.c_size_t)
HGDIOBJ = getattr(wintypes, "HGDIOBJ", wintypes.HANDLE)
HCURSOR = getattr(wintypes, "HCURSOR", wintypes.HANDLE)
HICON = getattr(wintypes, "HICON", wintypes.HANDLE)
HBRUSH = getattr(wintypes, "HBRUSH", wintypes.HANDLE)
HMENU = getattr(wintypes, "HMENU", wintypes.HANDLE)
HINSTANCE = getattr(wintypes, "HINSTANCE", wintypes.HANDLE)
HMODULE = getattr(wintypes, "HMODULE", wintypes.HANDLE)
HBITMAP = getattr(wintypes, "HBITMAP", wintypes.HANDLE)
HDC = getattr(wintypes, "HDC", wintypes.HANDLE)
COLORREF = getattr(wintypes, "COLORREF", wintypes.DWORD)


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_ubyte),
        ("BlendFlags", ctypes.c_ubyte),
        ("SourceConstantAlpha", ctypes.c_ubyte),
        ("AlphaFormat", ctypes.c_ubyte),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


WNDPROC = ctypes.WINFUNCTYPE(
    LRESULT,
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", HINSTANCE),
        ("hIcon", HICON),
        ("hCursor", HCURSOR),
        ("hbrBackground", HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


OVERLAY = None
WNDPROC_REF = None


def log_debug(message):
    try:
        with open(HUD_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(message + "\n")
    except OSError:
        pass


def get_env_float(name, default):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        log_debug(f"Invalid float for {name}: {raw!r}, fallback={default}")
        return default
    if value <= 0:
        log_debug(f"Non-positive float for {name}: {raw!r}, fallback={default}")
        return default
    return value


def enable_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        log_debug("DPI awareness enabled via shcore")
        return
    except Exception:
        pass
    try:
        user32.SetProcessDPIAware()
        log_debug("DPI awareness enabled via user32")
    except Exception:
        log_debug("DPI awareness setup skipped")


def get_screen_scale():
    screen_width = max(1, int(user32.GetSystemMetrics(SM_CXSCREEN)))
    screen_height = max(1, int(user32.GetSystemMetrics(SM_CYSCREEN)))
    base_scale = min(screen_width / BASE_SCREEN_WIDTH, screen_height / BASE_SCREEN_HEIGHT)
    extra_scale = get_env_float(HUD_EXTRA_SCALE_ENV, 1.0)
    scale = base_scale * extra_scale
    log_debug(
        f"HUD screen size {screen_width}x{screen_height}, "
        f"base_scale={base_scale:.4f}, extra_scale={extra_scale:.4f}, final_scale={scale:.4f}"
    )
    return scale, screen_width, screen_height


user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = wintypes.ATOM
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    HMENU,
    HINSTANCE,
    wintypes.LPVOID,
]
user32.CreateWindowExW.restype = wintypes.HWND
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.SetTimer.argtypes = [wintypes.HWND, UINT_PTR, wintypes.UINT, wintypes.LPVOID]
user32.SetTimer.restype = UINT_PTR
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.UpdateWindow.argtypes = [wintypes.HWND]
user32.UpdateWindow.restype = wintypes.BOOL
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.DestroyWindow.restype = wintypes.BOOL
user32.PostQuitMessage.argtypes = [ctypes.c_int]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.TranslateMessage.restype = wintypes.BOOL
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.restype = LRESULT
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, HDC]
user32.ReleaseDC.restype = ctypes.c_int
user32.UpdateLayeredWindow.argtypes = [
    wintypes.HWND,
    HDC,
    ctypes.POINTER(POINT),
    ctypes.POINTER(SIZE),
    HDC,
    ctypes.POINTER(POINT),
    COLORREF,
    ctypes.POINTER(BLENDFUNCTION),
    wintypes.DWORD,
]
user32.UpdateLayeredWindow.restype = wintypes.BOOL
gdi32.CreateCompatibleDC.argtypes = [HDC]
gdi32.CreateCompatibleDC.restype = HDC
gdi32.CreateDIBSection.argtypes = [HDC, ctypes.POINTER(BITMAPINFO), wintypes.UINT, ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
gdi32.CreateDIBSection.restype = HBITMAP
gdi32.SelectObject.argtypes = [HDC, HGDIOBJ]
gdi32.SelectObject.restype = HGDIOBJ
gdi32.DeleteObject.argtypes = [HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.restype = wintypes.BOOL
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = HMODULE
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.WaitForSingleObject.restype = wintypes.DWORD
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL


def load_font(size, monospace=False):
    if monospace:
        candidates = [
            r"C:\Windows\Fonts\consolab.ttf",
            r"C:\Windows\Fonts\consola.ttf",
            r"C:\Windows\Fonts\msyhbd.ttc",
            r"C:\Windows\Fonts\msyhui.ttc",
            r"C:\Windows\Fonts\msyh.ttc",
        ]
    else:
        candidates = [
            r"C:\Windows\Fonts\msyhbd.ttc",
            r"C:\Windows\Fonts\msyhui.ttc",
            r"C:\Windows\Fonts\msyh.ttc",
            r"C:\Windows\Fonts\simhei.ttf",
            r"C:\Windows\Fonts\consola.ttf",
            r"C:\Windows\Fonts\consolab.ttf",
        ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


class HudOverlay:
    def __init__(self, parent_pid=0):
        self.scale, self.screen_width, self.screen_height = get_screen_scale()
        self.left = self._scaled(BASE_LEFT)
        self.top = self._scaled(BASE_TOP)
        self.padding_x = self._scaled(BASE_PADDING_X)
        self.padding_y = self._scaled(BASE_PADDING_Y)
        self.line_spacing = self._scaled(BASE_LINE_SPACING)
        self.stroke_width = self._scaled(BASE_STROKE_WIDTH)
        self.min_width = self._scaled(BASE_MIN_WIDTH)
        self.queue = queue.Queue()
        self.lines = ["[HUD] 已连接，等待数据..."]
        self.font = load_font(self._scaled(BASE_FONT_SIZE))
        self.small_font = load_font(self._scaled(BASE_SMALL_FONT_SIZE))
        self.state_font = load_font(self._scaled(BASE_STATE_FONT_SIZE))
        self.state_small_font = load_font(self._scaled(BASE_STATE_SMALL_FONT_SIZE))
        self.state_mono_font = load_font(self._scaled(BASE_STATE_SMALL_FONT_SIZE), monospace=True)
        self.state_action_font = load_font(self._scaled(BASE_ACTION_FONT_SIZE))
        self.hwnd = None
        self.parent_pid = int(parent_pid or 0)
        self.last_heartbeat = 0.0
        self.state_payload = {}
        self.last_redraw_at = 0.0
        self.needs_redraw = False
        self.measure_cache = {}
        self.measure_image = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        self.measure_draw = ImageDraw.Draw(self.measure_image)
        log_debug(f"HUD starting. parent_pid={self.parent_pid}")
        self._register_window_class()
        self._create_window()
        self._redraw()
        if self.parent_pid > 0:
            thread = threading.Thread(target=self._watch_parent_process, daemon=True)
            thread.start()

    def _scaled(self, value, minimum=1):
        return max(minimum, int(round(value * self.scale)))

    def _register_window_class(self):
        global WNDPROC_REF
        WNDPROC_REF = WNDPROC(self._wndproc)
        hinst = kernel32.GetModuleHandleW(None)
        wndclass = WNDCLASSW()
        wndclass.lpfnWndProc = WNDPROC_REF
        wndclass.hInstance = hinst
        wndclass.lpszClassName = CLASS_NAME
        atom = user32.RegisterClassW(ctypes.byref(wndclass))
        log_debug(f"RegisterClassW -> {atom}")

    def _create_window(self):
        hinst = kernel32.GetModuleHandleW(None)
        ex_style = (
            WS_EX_LAYERED
            | WS_EX_TRANSPARENT
            | WS_EX_TOOLWINDOW
            | WS_EX_TOPMOST
            | WS_EX_NOACTIVATE
        )
        self.hwnd = user32.CreateWindowExW(
            ex_style,
            CLASS_NAME,
            "Majsoul HUD",
            WS_POPUP,
            self.left,
            self.top,
            1,
            1,
            None,
            None,
            hinst,
            None,
        )
        log_debug(f"CreateWindowExW hwnd={self.hwnd}")
        user32.SetTimer(self.hwnd, 1, 30, None)
        user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
        user32.UpdateWindow(self.hwnd)

    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_NCHITTEST:
            return HTTRANSPARENT
        if msg == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        if msg == WM_TIMER:
            self._drain_queue()
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _measure(self, line, font=None, stroke_width=None):
        font = font or self.font
        stroke_width = self.stroke_width if stroke_width is None else stroke_width
        cache_key = (id(font), stroke_width, line)
        cached = self.measure_cache.get(cache_key)
        if cached is not None:
            return cached
        left, top, right, bottom = self.measure_draw.textbbox((0, 0), line, font=font, stroke_width=stroke_width)
        measured = (right - left, bottom - top)
        self.measure_cache[cache_key] = measured
        return measured

    def _measure_spans(self, spans):
        width = 0
        height = 0
        for span in spans:
            span_width, span_height = self._measure(
                span["text"],
                font=span.get("font") or self.font,
                stroke_width=span.get("stroke_width", self.stroke_width),
            )
            width += span_width
            height = max(height, span_height)
        return width, height

    def _render_spans(self, draw, x, y, spans):
        cursor = x
        for span in spans:
            text = span["text"]
            font = span.get("font") or self.font
            fill = span.get("fill", TEXT_COLOR)
            stroke_width = span.get("stroke_width", self.stroke_width)
            draw.text(
                (cursor, y),
                text,
                font=font,
                fill=fill,
                stroke_width=stroke_width,
                stroke_fill=OUTLINE_COLOR,
            )
            span_width, _ = self._measure(text, font=font, stroke_width=stroke_width)
            cursor += span_width

    def _visible_count_rows(self, visible_counts):
        groups = [
            ("万", ["1m", "2m", "3m", "4m", "5m", "6m", "7m", "8m", "9m"]),
            ("筒", ["1p", "2p", "3p", "4p", "5p", "6p", "7p", "8p", "9p"]),
            ("索", ["1s", "2s", "3s", "4s", "5s", "6s", "7s", "8s", "9s"]),
            ("字", ["1z", "2z", "3z", "4z", "5z", "6z", "7z"]),
        ]
        rows = []
        for label, tiles in groups:
            row_text = "  ".join(f"{tile}:{(visible_counts or {}).get(tile, 0)}" for tile in tiles)
            rows.append(
                [
                    {
                        "text": f"已现牌{label}: ",
                        "fill": STATE_LABEL_COLOR,
                        "font": self.state_small_font,
                        "stroke_width": self._scaled(1),
                    },
                    {
                        "text": row_text,
                        "fill": STATE_SMALL_VALUE_COLOR,
                        "font": self.state_mono_font,
                        "stroke_width": self._scaled(1),
                    },
                ]
            )
        return rows

    def _build_state_lines(self):
        payload = self.state_payload or {}
        tedashi = payload.get("tedashi_counts") or [0, 0, 0, 0]
        turn_index = payload.get("turn_index", 0)
        self_seat = payload.get("self_seat")
        self_seat_text = f"S{self_seat}" if isinstance(self_seat, int) else "S?"
        self_hand = sorted((payload.get("self_hand") or []), key=lambda tile: (tile[1], 5 if tile.startswith("0") else int(tile[0])) if isinstance(tile, str) and len(tile) >= 2 else ("?", 99))
        self_melds = payload.get("self_melds") or []
        visible_counts = payload.get("visible_counts") or {}
        algo_eval = payload.get("algo_current_eval") or {}
        recommended_eval = payload.get("algo_recommended_eval") or {}
        self_tingpais = payload.get("self_tingpais") or {}
        recommended_action = payload.get("algo_recommended_action") or "-"

        def fmt_score(value, digits):
            if value is None:
                return "-"
            return f"{value:.{digits}f}"

        def fmt_arrow(name, current, recommended, digits=1):
            current_text = fmt_score(current, digits)
            if not recommended_eval:
                return f"{name} {current_text}"
            return f"{name} {current_text} -> {fmt_score(recommended, digits)}"

        current_eff_total = self_tingpais.get("total", algo_eval.get("necessary_total"))
        current_eff_types = self_tingpais.get("types", algo_eval.get("necessary_types"))
        recommended_eff_total = recommended_eval.get("necessary_total")
        recommended_eff_types = recommended_eval.get("necessary_types")
        current_eff_summary = (
            f"{current_eff_total if current_eff_total is not None else '-'}张/"
            f"{current_eff_types if current_eff_types is not None else '-'}种"
            if algo_eval
            else "-"
        )
        recommended_eff_summary = (
            f"{recommended_eff_total if recommended_eff_total is not None else '-'}张/"
            f"{recommended_eff_types if recommended_eff_types is not None else '-'}种"
            if recommended_eval
            else ""
        )
        effective_tiles_text = self_tingpais.get("text") or algo_eval.get("necessary_tiles_text") or "-"
        if recommended_eval:
            effective_tiles_text = (
                f"{current_eff_summary} -> {recommended_eff_summary}  "
                f"{effective_tiles_text} -> {recommended_eval.get('necessary_tiles_text') or '-'}"
            )
        else:
            effective_tiles_text = f"{current_eff_summary}  {effective_tiles_text}"
        algo_eval_text = "  ".join(
            [
                fmt_arrow("向听", algo_eval.get("shanten"), recommended_eval.get("shanten"), 0),
                fmt_arrow("期待", algo_eval.get("exp_score"), recommended_eval.get("exp_score"), 1),
                fmt_arrow("胜率", algo_eval.get("win_prob"), recommended_eval.get("win_prob"), 3),
                fmt_arrow("听牌率", algo_eval.get("tenpai_prob"), recommended_eval.get("tenpai_prob"), 3),
            ]
        )

        lines = []
        tedashi_spans = [
            {"text": "当前巡目: ", "fill": STATE_LABEL_COLOR, "font": self.state_font},
            {"text": str(turn_index) + "    ", "fill": STATE_VALUE_COLOR, "font": self.state_font},
            {"text": "手切次数: ", "fill": STATE_LABEL_COLOR, "font": self.state_font},
        ]
        for idx, count in enumerate(tedashi):
            tedashi_spans.append({"text": f"S{idx}:", "fill": STATE_LABEL_COLOR, "font": self.state_font})
            tedashi_spans.append({"text": str(count) + "  ", "fill": STATE_VALUE_COLOR, "font": self.state_font})
        lines.append(tedashi_spans)

        self_meld_text = " ".join(
            f"[{meld.get('type', '')}:{' '.join(meld.get('tiles', []))}]"
            for meld in self_melds
        ) or "-"
        lines.append(
            [
                {"text": f"自家牌组({self_seat_text}): ", "fill": STATE_LABEL_COLOR, "font": self.state_font},
                {
                    "text": (" ".join(self_hand) if self_hand else "-") + ("  " if self_meld_text != "-" else ""),
                    "fill": STATE_VALUE_COLOR,
                    "font": self.state_font,
                },
                {"text": self_meld_text if self_meld_text != "-" else "", "fill": STATE_VALUE_COLOR, "font": self.state_font},
            ]
        )
        lines.extend(self._visible_count_rows(visible_counts))
        lines.append(
            [
                {"text": "当前牌效: ", "fill": STATE_LABEL_COLOR, "font": self.state_font},
                {"text": algo_eval_text, "fill": STATE_VALUE_COLOR, "font": self.state_font},
            ]
        )
        lines.append(
            [
                {"text": "有效牌: ", "fill": STATE_LABEL_COLOR, "font": self.state_small_font},
                {"text": effective_tiles_text, "fill": STATE_SMALL_VALUE_COLOR, "font": self.state_small_font},
            ]
        )
        lines.append(
            [
                {"text": recommended_action, "fill": STATE_VALUE_COLOR, "font": self.state_action_font},
            ]
        )
        return lines

    def _compose_image(self):
        state_lines = self._build_state_lines()
        log_lines = self.lines[-MAX_LOG_LINES:]
        render_items = list(state_lines)
        if log_lines:
            render_items.append(
                [{"text": "-" * 36, "fill": STATE_LABEL_COLOR, "font": self.small_font, "stroke_width": self._scaled(1)}]
            )
            render_items.extend(([{"text": line, "fill": TEXT_COLOR, "font": self.font}] for line in log_lines))

        if not render_items:
            return Image.new("RGBA", (1, 1), (0, 0, 0, 0))

        widths = []
        heights = []
        for spans in render_items:
            width, height = self._measure_spans(spans)
            widths.append(max(1, width))
            heights.append(max(1, height))

        line_heights = [height + self.line_spacing for height in heights]
        width = max(widths + [self.min_width]) + self.padding_x * 2
        height = sum(line_heights) + self.padding_y * 2

        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        y = self.padding_y
        for index, spans in enumerate(render_items):
            self._render_spans(draw, self.padding_x, y, spans)
            y += line_heights[index]

        return image

    def _redraw(self):
        image = self._compose_image()
        width, height = image.size
        data = image.tobytes("raw", "BGRA")

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = -height
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB

        bits = ctypes.c_void_p()
        screen_dc = user32.GetDC(None)
        mem_dc = gdi32.CreateCompatibleDC(screen_dc)
        bitmap = gdi32.CreateDIBSection(mem_dc, ctypes.byref(bmi), DIB_RGB_COLORS, ctypes.byref(bits), None, 0)
        old_bitmap = gdi32.SelectObject(mem_dc, bitmap)

        ctypes.memmove(bits, data, len(data))

        dst_pos = POINT(self.left, self.top)
        src_pos = POINT(0, 0)
        size = SIZE(width, height)
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)

        user32.UpdateLayeredWindow(
            self.hwnd,
            screen_dc,
            ctypes.byref(dst_pos),
            ctypes.byref(size),
            mem_dc,
            ctypes.byref(src_pos),
            0,
            ctypes.byref(blend),
            ULW_ALPHA,
        )
        self.last_redraw_at = time.monotonic()
        self.needs_redraw = False

        gdi32.SelectObject(mem_dc, old_bitmap)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(None, screen_dc)

    def _drain_queue(self):
        changed = False
        while True:
            try:
                line = self.queue.get_nowait()
            except queue.Empty:
                break

            if line == "__HUD_PING__":
                self.last_heartbeat = time.monotonic()
                continue
            if line == "__HUD_CLEAR__":
                self.lines = []
            else:
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    payload = None

                if isinstance(payload, dict) and payload.get("kind") == "state":
                    self.state_payload = payload.get("payload") or {}
                    changed = True
                    continue
                self.lines.append(line)
            changed = True

        if changed:
            self.lines = self.lines[-MAX_LOG_LINES:]
            self.needs_redraw = True

        if self.needs_redraw and (time.monotonic() - self.last_redraw_at) >= REDRAW_INTERVAL_SECONDS:
            self._redraw()

        if self.last_heartbeat and (time.monotonic() - self.last_heartbeat) > HEARTBEAT_TIMEOUT_SECONDS:
            log_debug("Heartbeat timeout, closing HUD")
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)

    def run(self):
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    def _watch_parent_process(self):
        handle = kernel32.OpenProcess(SYNCHRONIZE, False, self.parent_pid)
        if not handle:
            log_debug(f"OpenProcess failed for parent_pid={self.parent_pid}")
            return

        result = kernel32.WaitForSingleObject(handle, 0xFFFFFFFF)
        kernel32.CloseHandle(handle)
        log_debug(f"Parent process wait completed. result={result}")
        if result == WAIT_OBJECT_0:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)


def socket_server(target_queue):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((HOST, PORT))
        log_debug(f"UDP bind ok {HOST}:{PORT}")
    except OSError:
        log_debug(f"UDP bind failed on {HOST}:{PORT}")
        return

    while True:
        try:
            data, _ = sock.recvfrom(65535)
        except OSError:
            break
        text = data.decode("utf-8", errors="replace")
        log_debug(f"UDP recv: {text[:120]}")
        target_queue.put(text)


def parse_args():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--parent-pid", type=int, default=0)
    parser.add_argument("--majsoul-hud", action="store_true")
    return parser.parse_args()


def main():
    global OVERLAY
    args = parse_args()
    log_debug("=" * 30)
    enable_dpi_awareness()
    OVERLAY = HudOverlay(parent_pid=args.parent_pid)
    thread = threading.Thread(target=socket_server, args=(OVERLAY.queue,), daemon=True)
    thread.start()
    OVERLAY.run()


if __name__ == "__main__":
    main()
