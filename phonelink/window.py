"""Native window controls for the frameless PhoneLink window (pywebview js_api)."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

_WM_NCLBUTTONDOWN = 0x00A1
_HT = {
    "caption": 2, "left": 10, "right": 11, "top": 12, "topleft": 13,
    "topright": 14, "bottom": 15, "bottomleft": 16, "bottomright": 17,
}


class WindowApi:
    def __init__(self) -> None:
        self._window = None

    def bind(self, window) -> None:
        self._window = window

    def _hwnd(self) -> int | None:
        try:
            return int(self._window.native.Handle.ToInt64())
        except Exception:
            return None

    def _native_drag(self, hit: int) -> None:
        hwnd = self._hwnd()
        if hwnd:
            ctypes.windll.user32.ReleaseCapture()
            ctypes.windll.user32.SendMessageW(wintypes.HWND(hwnd), _WM_NCLBUTTONDOWN, hit, 0)

    def start_drag(self) -> None:
        self._native_drag(_HT["caption"])

    def start_resize(self, edge: str) -> None:
        if edge in _HT and edge != "caption" and not self.is_maximized():
            self._native_drag(_HT[edge])

    def is_maximized(self) -> bool:
        hwnd = self._hwnd()
        return bool(hwnd and ctypes.windll.user32.IsZoomed(wintypes.HWND(hwnd)))

    def minimize(self) -> None:
        self._window.minimize()

    def toggle_maximize(self) -> bool:
        if self.is_maximized():
            self._window.restore()
        else:
            self._window.maximize()
        return self.is_maximized()

    def close(self) -> None:
        self._window.destroy()
