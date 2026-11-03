"""Native window controls for the frameless PhoneLink window (pywebview js_api).

pywebview's Window methods marshal onto the UI thread, so they are safe from
the js_api worker thread. Dragging uses pywebview's own drag regions
(.pywebview-drag-region); only edge resizing needs a Win32 message.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

_user32 = ctypes.windll.user32
_WM_NCLBUTTONDOWN = 0x00A1
_HT = {"left": 10, "right": 11, "top": 12, "topleft": 13, "topright": 14,
       "bottom": 15, "bottomleft": 16, "bottomright": 17}

TITLE = "PhoneLink"


class WindowApi:
    def __init__(self) -> None:
        self._window = None
        self._maximized = False
        self._fullscreen = False

    def bind(self, window) -> None:
        self._window = window
        window.events.maximized += lambda: setattr(self, "_maximized", True)
        window.events.restored += lambda: setattr(self, "_maximized", False)

    def _hwnd(self) -> int | None:
        return _user32.FindWindowW(None, TITLE) or None

    def start_resize(self, edge: str) -> None:
        hwnd = self._hwnd()
        if hwnd and edge in _HT and not self._maximized and not self._fullscreen:
            _user32.ReleaseCapture()
            _user32.SendMessageW(wintypes.HWND(hwnd), _WM_NCLBUTTONDOWN, _HT[edge], 0)

    def is_maximized(self) -> bool:
        return self._maximized

    def minimize(self) -> None:
        self._window.minimize()

    def toggle_maximize(self) -> bool:
        if self._maximized:
            self._window.restore()
            self._maximized = False
        else:
            self._window.maximize()
            self._maximized = True
        return self._maximized

    def set_fullscreen(self, on: bool) -> bool:
        if bool(on) != self._fullscreen:
            self._window.toggle_fullscreen()
            self._fullscreen = bool(on)
        return self._fullscreen

    def set_on_top(self, on: bool) -> None:
        self._window.on_top = bool(on)

    def close(self) -> None:
        self._window.destroy()
