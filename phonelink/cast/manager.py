"""Owns the wired cast: device discovery, one session at a time, and fan-out
of encoded video and PCM audio to every connected viewer."""

from __future__ import annotations

import base64
import ctypes
import json
import logging
import struct
import threading
import time
from typing import Callable

from . import usb_session, wire

log = logging.getLogger(__name__)

def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


# Wired casting opens the device through libusb0, which Start.bat prepares
# when run as administrator.
IS_ADMIN = _is_admin()

# Media message types sent to viewers (first byte of each binary message).
MSG_VIDEO_CONFIG = 1
MSG_VIDEO = 2
MSG_AUDIO = 3

Listener = Callable[[bytes | str], None]


def _is_keyframe(avcc: bytes) -> bool:
    pos = 0
    while pos + 5 <= len(avcc):
        size = int.from_bytes(avcc[pos : pos + 4], "big")
        if avcc[pos + 4] & 0x1F == 5:
            return True
        pos += 4 + size
    return False


class CastManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._listeners: set[Listener] = set()
        self._session: usb_session.UsbCastSession | None = None
        self._thread: threading.Thread | None = None
        self._video_config: dict | None = None
        self._devices: list[dict] = []
        self.state = {"phase": "idle", "detail": "", "device": None, "error": None}

    # ------------------------------------------------------------ viewers

    def add_listener(self, listener: Listener) -> None:
        with self._lock:
            self._listeners.add(listener)
        listener(json.dumps({"type": "state", **self.snapshot()}))
        if self._video_config:
            listener(self._config_message())

    def remove_listener(self, listener: Listener) -> None:
        with self._lock:
            self._listeners.discard(listener)

    def _broadcast(self, message: bytes | str) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(message)
            except Exception:  # a closed viewer must not stop the stream
                log.debug("listener failed", exc_info=True)

    def _publish_state(self) -> None:
        self._broadcast(json.dumps({"type": "state", **self.snapshot()}))

    def snapshot(self) -> dict:
        return {
            **self.state,
            "admin": IS_ADMIN,
            "devices": self._devices,
            "video": {k: v for k, v in (self._video_config or {}).items() if k != "description"} or None,
        }

    def _set_state(self, phase: str, detail: str = "", error: str | None = None) -> None:
        self.state.update(phase=phase, detail=detail, error=error)
        self._publish_state()

    # ------------------------------------------------------------ devices

    # ------------------------------------------------------------ casting

    def start(self, device_id: str | None = None) -> dict:
        if not IS_ADMIN:
            self._set_state("error", error="Close PhoneLink and run Start.bat as administrator.")
            return self.snapshot()
        with self._lock:
            if self._session is not None:
                return self.snapshot()
        devices = usb_session.list_devices()
        if device_id:
            devices = [d for d in devices if d.serial.strip("\x00") == device_id] or devices
        if not devices:
            self._set_state(
                "error",
                error="PhoneLink can't open the device over USB. Install the USB driver, then reconnect the cable.",
            )
            return self.snapshot()
        target = devices[0]
        self.state["device"] = {"id": target.serial.strip("\x00"), "name": target.product}
        self._video_config = None
        session = usb_session.UsbCastSession(
            target.serial, self._on_video, self._on_audio, on_state=self._on_session_state
        )
        self._session = session
        self._thread = threading.Thread(target=self._run, args=(session,), name="usb-cast", daemon=True)
        self._set_state("connecting", "Opening screen capture on the device")
        self._thread.start()
        return self.snapshot()

    def stop(self) -> dict:
        session = self._session
        if session is not None:
            session.stop()
            if self._thread is not None:
                self._thread.join(6)
        return self.snapshot()

    def _run(self, session: usb_session.UsbCastSession) -> None:
        try:
            session.run()
            self._set_state("idle", "Casting stopped")
        except Exception as error:
            log.exception("cast session failed")
            self._set_state("error", error=str(error))
        finally:
            self._session = None
            self._video_config = None

    def _on_session_state(self, phase: str, detail: str) -> None:
        if phase == "waiting":
            detail = "Unlock the device and keep it unlocked"
        self._set_state(phase, detail)

    def _config_message(self) -> str:
        return json.dumps({"type": "video-config", **self._video_config})

    def _on_video(self, buf: wire.SampleBuffer) -> None:
        received = time.time() * 1000.0
        fmt = buf.format
        if fmt is not None and fmt.avcc:
            config = {
                "codec": fmt.codec_string,
                "description": base64.b64encode(fmt.avcc).decode("ascii"),
                "width": fmt.width,
                "height": fmt.height,
            }
            if config != self._video_config:
                self._video_config = config
                self._broadcast(self._config_message())
                self._publish_state()
        if not buf.data:
            return
        if self.state["phase"] != "streaming":
            self._set_state("streaming")
        header = struct.pack("<BBdd", MSG_VIDEO, 1 if _is_keyframe(buf.data) else 0, buf.pts.seconds, received)
        self._broadcast(header + buf.data)

    def _on_audio(self, buf: wire.SampleBuffer) -> None:
        if not buf.data:
            return
        header = struct.pack("<BBdd", MSG_AUDIO, 0, buf.pts.seconds, time.time() * 1000.0)
        self._broadcast(header + buf.data)
