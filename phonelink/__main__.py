"""PhoneLink desktop entry point: local server + native window."""

from __future__ import annotations

import ctypes
import logging
import os
import sys
import threading

from phonelink.cast.manager import CastManager
from phonelink.paths import APP_ROOT
from phonelink.server import HOST, PORT, serve_forever
from phonelink.window import WindowApi

# Hardware video decode and sound without a click first.
os.environ.setdefault(
    "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS",
    "--enable-features=PlatformHEVCDecoderSupport --autoplay-policy=no-user-gesture-required",
)


def _dark_title_bar(window) -> None:
    """Dark mode + rounded corners for the frameless window (Windows 11 DWM)."""
    try:
        hwnd = window.native.Handle.ToInt32()
        corner = ctypes.c_int(2)  # DWMWCP_ROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(corner), ctypes.sizeof(corner))
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(APP_ROOT / "phonelink.log", encoding="utf-8")],
    )
    manager = CastManager()
    ready = threading.Event()
    threading.Thread(target=serve_forever, args=(manager, ready), name="server", daemon=True).start()
    if not ready.wait(10):
        sys.exit("PhoneLink could not start its local server.")

    if "--headless" in sys.argv:
        print(f"PhoneLink running at http://{HOST}:{PORT}/")
        threading.Event().wait()

    import webview

    api = WindowApi()
    window = webview.create_window(
        "PhoneLink",
        f"http://{HOST}:{PORT}/",
        js_api=api,
        width=1180,
        height=760,
        min_size=(640, 420),
        frameless=True,
        easy_drag=False,
        background_color="#0b0c0e",
    )
    api.bind(window)
    window.events.shown += lambda: _dark_title_bar(window)
    try:
        webview.start(gui="edgechromium", private_mode=False, storage_path=str(APP_ROOT / ".webview"))
    finally:
        manager.stop()


if __name__ == "__main__":
    main()
