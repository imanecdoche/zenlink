"""Native window controls for the frameless PhoneLink window (pywebview js_api).

js_api calls arrive on a worker thread, where touching the WinForms form
(window.native) throws a cross-thread error. So the HWND is looked up with
Win32 (FindWindowW) and every move/size goes through Win32 messages.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

_user32 = ctypes.windll.user32
_WM_NCLBUTTONDOWN = 0x00A1
_WM_SYSCOMMAND = 0x0112
_SC_MINIMIZE, _SC_MAXIMIZE, _SC_RESTORE, _SC_CLOSE = 0xF020, 0xF030, 0xF120, 0xF060
_HT = {
    "caption": 2, "left": 10, "right": 11, "top": 12, "topleft": 13,
    "topright": 14, "bottom": 15, "bottomleft": 16, "bottomright": 17,
}

TITLE = "PhoneLink"


class WindowApi:
    def __init__(self) -> None:
        self._hwnd: int | None = None

    def _handle(self) -> int | None:
        if self._hwnd and _user32.IsWindow(wintypes.HWND(self._hwnd)):
            return self._hwnd
        hwnd = _user32.FindWindowW(None, TITLE)
        self._hwnd = hwnd or None
        return self._hwnd

    def _post(self, msg: int, wparam: int, lparam: int = 0) -> None:
        hwnd = self._handle()
        if hwnd:
            _user32.ReleaseCapture()
            _user32.PostMessageW(wintypes.HWND(hwnd), msg, wparam, lparam)

    def _drag(self, hit: int) -> None:
        hwnd = self._handle()
        if hwnd:
            _user32.ReleaseCapture()
            _user32.SendMessageW(wintypes.HWND(hwnd), _WM_NCLBUTTONDOWN, hit, 0)

    def start_drag(self) -> None:
        self._drag(_HT["caption"])

    def start_resize(self, edge: str) -> None:
        if edge in _HT and edge != "caption" and not self.is_maximized():
            self._drag(_HT[edge])

    def is_maximized(self) -> bool:
        hwnd = self._handle()
        return bool(hwnd and _user32.IsZoomed(wintypes.HWND(hwnd)))

    def minimize(self) -> None:
        self._post(_WM_SYSCOMMAND, _SC_MINIMIZE)

    def toggle_maximize(self) -> bool:
        maximized = self.is_maximized()
        self._post(_WM_SYSCOMMAND, _SC_RESTORE if maximized else _SC_MAXIMIZE)
        return not maximized

    def set_on_top(self, on: bool) -> None:
        hwnd = self._handle()
        if hwnd:
            HWND_TOPMOST, HWND_NOTOPMOST, flags = -1, -2, 0x0001 | 0x0002 | 0x0010  # NOSIZE|NOMOVE|NOACTIVATE
            _user32.SetWindowPos(wintypes.HWND(hwnd), HWND_TOPMOST if on else HWND_NOTOPMOST, 0, 0, 0, 0, flags)

    def close(self) -> None:
        self._post(_WM_SYSCOMMAND, _SC_CLOSE)
