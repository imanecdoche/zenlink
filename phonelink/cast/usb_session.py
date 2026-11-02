"""Wired cast: talk Apple's USB screen-capture protocol to an iPhone/iPad.

Flow: switch the device to its hidden QuickTime USB configuration, claim the
vendor interface (class 0xFF, subclass 0x2A), answer the device's clock and
format handshake, then receive H.264 access units (FEED) and 48 kHz stereo
PCM (EAT!) until stopped.
"""

from __future__ import annotations

import logging
import struct
import threading
import time
from dataclasses import dataclass
from typing import Callable

import libusb_package
import usb.core
import usb.util

from . import lockdown, models, usbmux, wire

log = logging.getLogger(__name__)

APPLE_VID = 0x05AC
QT_SUBCLASS = 0x2A
MUX_SUBCLASS = 0xFE
VENDOR_CLASS = 0xFF


@dataclass
class CastDevice:
    serial: str
    product: str

    @property
    def udid(self) -> str:
        s = self.serial.strip("\x00")
        return f"{s[:8]}-{s[8:]}" if len(s) == 24 else s


_BACKEND = None


def _backend():
    """libusb-win32 (libusb0.dll), the same API TikTok LIVE Studio's qcast uses
    with the libusb0 driver bound to the device; libusb-1.0 is the fallback."""
    global _BACKEND
    if _BACKEND is None:
        import os
        import usb.backend.libusb0

        system_dll = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "System32", "libusb0.dll")
        backend = None
        if os.environ.get("PHONELINK_USB_BACKEND") != "libusb1" and os.path.exists(system_dll):
            backend = usb.backend.libusb0.get_backend(find_library=lambda _name: system_dll)
        _BACKEND = backend or libusb_package.get_libusb1_backend()
    return _BACKEND


def _configs(dev) -> tuple[int | None, int | None]:
    mux = qt = None
    for cfg in dev:
        subclasses = {(i.bInterfaceClass, i.bInterfaceSubClass) for i in cfg}
        if (VENDOR_CLASS, QT_SUBCLASS) in subclasses:
            qt = cfg.bConfigurationValue
        elif (VENDOR_CLASS, MUX_SUBCLASS) in subclasses:
            mux = cfg.bConfigurationValue
    return mux, qt


def list_devices() -> list[CastDevice]:
    found = []
    for dev in usb.core.find(find_all=True, idVendor=APPLE_VID, backend=_backend()) or []:
        try:
            serial = usb.util.get_string(dev, dev.iSerialNumber) or ""
            product = usb.util.get_string(dev, dev.iProduct) or "iOS device"
        except (usb.core.USBError, ValueError):
            continue
        if _configs(dev)[0] is None and _configs(dev)[1] is None:
            continue
        found.append(CastDevice(serial, product))
        usb.util.dispose_resources(dev)
    return found


def _find(serial: str):
    for dev in usb.core.find(find_all=True, idVendor=APPLE_VID, backend=_backend()) or []:
        try:
            if (usb.util.get_string(dev, dev.iSerialNumber) or "").strip("\x00") == serial.strip("\x00"):
                return dev
        except (usb.core.USBError, ValueError):
            pass
    return None


def _is_timeout(error: usb.core.USBError) -> bool:
    # libusb-1.0 raises USBTimeoutError; libusb-win32 reports a plain error.
    return isinstance(error, usb.core.USBTimeoutError) or "timeout" in str(error).lower()


class HostClock:
    """A CMClock running on host time, in nanoseconds."""

    def __init__(self, clock_id: int) -> None:
        self.id = clock_id
        self._start = time.perf_counter_ns()

    def now(self) -> wire.CMTime:
        return wire.CMTime(time.perf_counter_ns() - self._start, 1_000_000_000, 1, 0)


VideoCallback = Callable[[wire.SampleBuffer], None]
AudioCallback = Callable[[wire.SampleBuffer], None]


class UsbCastSession:
    def __init__(
        self,
        serial: str,
        on_video: VideoCallback,
        on_audio: AudioCallback,
        display_size: tuple[int, int] = (3840, 2160),
        on_state: Callable[[str, str], None] | None = None,
    ) -> None:
        self.serial = serial
        self.on_video = on_video
        self.on_audio = on_audio
        self.display_size = display_size
        self.on_state = on_state or (lambda state, detail: None)
        self._dev = None
        self._iface = None
        self._ep_in = None
        self._ep_out = None
        self._mux_cfg: int | None = None
        self._stop = threading.Event()
        self._released = threading.Event()
        self._write_lock = threading.Lock()
        self._need = b""
        self._clock: HostClock | None = None
        self._audio_clock: HostClock | None = None
        self._device_audio_clock = 0
        self._audio_start: tuple[wire.CMTime, wire.CMTime] | None = None
        self._audio_last: tuple[wire.CMTime, wire.CMTime] | None = None
        self.stats = {"video": 0, "audio": 0, "bytes": 0}

    # ---------------------------------------------------------------- USB

    def _activate(self) -> None:
        dev = _find(self.serial)
        if dev is None:
            raise RuntimeError("Device not found on USB. Plug it in and unlock it.")
        self._mux_cfg, qt = _configs(dev)
        self.on_state("activating", "Enabling screen capture on the device")
        # Always send the enable request (qcast: switch2QtConfiguration). A
        # capture configuration still listed from a previous session can be
        # stale on the device side, leaving the interface silent.
        try:
            dev.ctrl_transfer(0x40, 0x52, 0x00, 0x02, b"", timeout=1000)
        except usb.core.USBError as error:
            log.debug("enable QT config: %s (usually harmless)", error)
        usb.util.dispose_resources(dev)
        # qcast: "Configuration Switch Completed, Wait ReConnect". The device
        # drops off the bus (~0.5 s) and comes back as a new device (~1.4 s);
        # only the reconnected device has a live capture interface.
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline and _find(self.serial) is not None:
            time.sleep(0.1)
        dev = None
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            dev = _find(self.serial)
            if dev is not None and _configs(dev)[1] is not None:
                break
            time.sleep(0.2)
        else:
            raise RuntimeError("The device did not come back in screen-capture mode. Unlock it and try again.")
        time.sleep(1.0)  # let Windows finish binding the driver to the new device
        dev = _find(self.serial)
        self._mux_cfg, qt = _configs(dev)

        # qcast always selects the capture configuration, then claims the
        # interface and clears both endpoint halts.
        dev.set_configuration(qt)
        cfg = dev.get_active_configuration()
        iface = next(i for i in cfg if i.bInterfaceClass == VENDOR_CLASS and i.bInterfaceSubClass == QT_SUBCLASS)
        usb.util.claim_interface(dev, iface.bInterfaceNumber)
        ep_in = usb.util.find_descriptor(
            iface, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN
        )
        ep_out = usb.util.find_descriptor(
            iface, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
        )
        for ep in (ep_in, ep_out):
            try:
                dev.clear_halt(ep)
            except usb.core.USBError:
                pass
        self._dev, self._iface, self._ep_in, self._ep_out = dev, iface, ep_in, ep_out
        self._open_trust(dev, cfg)

    def _open_trust(self, dev, cfg) -> None:
        """Hold a trusted lockdown session over usbmux while capturing.

        With libusb0 bound there is no Apple usbmuxd, so PhoneLink speaks usbmux
        itself (as qcast does). Without a trusted session the device keeps the
        capture interface silent.
        """
        mux_iface = next(
            (i for i in cfg if i.bInterfaceClass == VENDOR_CLASS and i.bInterfaceSubClass == MUX_SUBCLASS), None
        )
        if mux_iface is None:
            log.warning("no usbmux interface in the capture configuration")
            return
        self.on_state("trust", "Checking that this PC is trusted")
        udid = self.serial.replace("\0", "")
        try:
            usb.util.claim_interface(dev, mux_iface.bInterfaceNumber)
            self._mux_iface = mux_iface
            ep_in = usb.util.find_descriptor(mux_iface, custom_match=lambda e: e.bEndpointAddress & 0x80)
            ep_out = usb.util.find_descriptor(mux_iface, custom_match=lambda e: not e.bEndpointAddress & 0x80)
            self._mux = usbmux.UsbMux(ep_in, ep_out)
            self._mux.start()
            client = lockdown.LockdownClient(self._mux.connect(usbmux.LOCKDOWN_PORT))
            client.query_type()
            try:
                product = client.get_value("ProductType")
                if product:
                    models.remember_product(udid, str(product))
            except lockdown.LockdownError:
                pass
            record = lockdown.load_pair_record(udid)
            if record is None:
                raise RuntimeError(
                    "This PC isn't trusted by the device yet. Connect it once with iTunes or "
                    "Apple Devices and tap Trust, then try again."
                )
            client.start_session(record)
            self._lockdown = client
            log.info("trusted lockdown session open")
        except (usbmux.MuxError, lockdown.LockdownError, usb.core.USBError) as error:
            log.warning("lockdown session failed: %s", error)
            text = str(error)
            if "PasswordProtected" in text or "DeviceLocked" in text:
                raise RuntimeError("Unlock the device and try again.") from error
            if "InvalidHostID" in text or "Pair" in text:
                raise RuntimeError(
                    "The device doesn't trust this PC anymore. Connect it once with iTunes or "
                    "Apple Devices, tap Trust, then try again."
                ) from error

    def _deactivate(self) -> None:
        dev = self._dev
        if dev is None:
            return
        if getattr(self, "_lockdown", None) is not None:
            self._lockdown.stop_session()
            self._lockdown = None
        if getattr(self, "_mux", None) is not None:
            self._mux.stop()
            self._mux = None
        if getattr(self, "_mux_iface", None) is not None:
            try:
                usb.util.release_interface(dev, self._mux_iface.bInterfaceNumber)
            except usb.core.USBError:
                pass
            self._mux_iface = None
        try:
            usb.util.release_interface(dev, self._iface.bInterfaceNumber)
        except (usb.core.USBError, AttributeError):
            pass
        # Leave the capture configuration in place. Sending the disable request
        # (0x52, index 0) leaves the device's capture function dead until it is
        # re-plugged, so the next session would never get a PING.
        usb.util.dispose_resources(dev)
        self._dev = None

    def _write(self, data: bytes, timeout: int = 2000) -> None:
        with self._write_lock:
            self._ep_out.write(data, timeout=timeout)

    def _try_write(self, data: bytes) -> bool:
        """Best-effort write; a device that is still locked simply doesn't take it."""
        try:
            self._write(data, timeout=100)
            return True
        except usb.core.USBError as error:
            if _is_timeout(error):
                return False
            raise

    # ------------------------------------------------------------ session

    def run(self) -> None:
        """Blocking: capture until stop() is called or the device goes away."""
        self._activate()
        self.on_state("waiting", "Unlock the device and tap Trust if it asks")
        buf = bytearray()
        self._pinged = False
        next_ping = 0.0
        try:
            while not self._stop.is_set():
                try:
                    # Same cadence as TikTok LIVE Studio's qcast: 16 KiB reads, 100 ms timeout.
                    chunk = self._ep_in.read(0x4000, timeout=100)
                except usb.core.USBError as error:
                    if not _is_timeout(error):
                        raise
                    # Like qcast, keep polling while the device is silent (locked,
                    # waiting for Trust) and offer an active PING; if the device
                    # doesn't take it yet, offer it again a second later.
                    now = time.monotonic()
                    if not self._pinged and now >= next_ping:
                        self._pinged = self._try_write(wire.ping_active())
                        log.debug("active PING %s", "accepted" if self._pinged else "not taken yet")
                        next_ping = now + 1.0
                    continue
                buf += chunk
                self.stats["bytes"] += len(chunk)
                while len(buf) >= 4:
                    length = wire.u32(buf)
                    if length < 8 or len(buf) < length:
                        break
                    packet = bytes(buf[4:length])
                    del buf[:length]
                    self._handle(packet)
        except usb.core.USBError as error:
            if not self._stop.is_set():
                raise RuntimeError(f"USB connection lost: {error}") from error
        finally:
            self._close_stream()
            self._deactivate()

    def stop(self) -> None:
        self._stop.set()

    def _close_stream(self) -> None:
        if self._ep_out is None:
            return
        try:
            self._write(wire.asyn(wire.HPA0, self._device_audio_clock))
            self._write(wire.asyn(wire.HPD0, wire.EMPTY_CF))
            self._released.wait(1.5)
            self._write(wire.asyn(wire.HPD0, wire.EMPTY_CF))
        except usb.core.USBError:
            pass

    # Packets arrive without their 4-byte length prefix.
    def _handle(self, p: bytes) -> None:
        kind = wire.u32(p)
        if kind == wire.PING:
            # A PING answering our active PING needs no reply (qcast: "Ignore").
            if not self._pinged:
                self._write(wire.ping())
                self._pinged = True
            self.on_state("handshake", "Device connected")
        elif kind == wire.SYNC:
            self._handle_sync(p)
        elif kind == wire.ASYN:
            self._handle_asyn(p)
        else:
            log.warning("unknown packet %r", p[:4])

    def _handle_sync(self, p: bytes) -> None:
        sub = wire.u32(p, 12)
        correlation = wire.u64(p, 16)
        body = p[24:]
        if sub == wire.CWPA:
            device_clock = wire.u64(body)
            self._device_audio_clock = device_clock
            self._audio_clock = HostClock(device_clock + 1000)
            w, h = self.display_size
            self._write(wire.hpd1(w, h))
            self._write(wire.hpd1(w, h))
            self._write(wire.reply_clock(correlation, self._audio_clock.id))
            self._write(wire.hpa1(device_clock))
        elif sub == wire.CVRP:
            device_clock = wire.u64(body)
            self._need = wire.need(device_clock)
            self._write(self._need)
            self._write(wire.reply_clock(correlation, device_clock + 0x1000AF))
        elif sub == wire.CLOK:
            clock_ref = wire.u64(p, 4) + 0x10000
            self._clock = HostClock(clock_ref)
            self._write(wire.reply_clock(correlation, clock_ref))
        elif sub == wire.TIME:
            now = (self._clock or HostClock(0)).now()
            self._write(wire.reply_time(correlation, now))
        elif sub == wire.AFMT:
            self._write(wire.reply_dict(correlation, {"Error": wire.n32(0)}))
        elif sub == wire.SKEW:
            self._write(wire.reply_skew(correlation, self._skew()))
        elif sub == wire.OG:
            self._write(wire.reply_empty(correlation))
            self.on_state("streaming", "")
        elif sub == wire.STOP:
            self._write(wire.reply_empty(correlation))
        else:
            log.warning("unknown sync %r", p[12:16])

    def _handle_asyn(self, p: bytes) -> None:
        sub = wire.u32(p, 12)
        if sub == wire.FEED:
            try:
                buf = wire.SampleBuffer.parse(p[16:], wire.MEDIA_VIDEO)
            except (ValueError, IndexError, struct.error) as error:
                log.debug("bad FEED: %s", error)
                if self._need:
                    self._write(self._need)
                return
            self.stats["video"] += 1
            self.on_video(buf)
            if self._need:
                self._write(self._need)
        elif sub == wire.EAT:
            try:
                buf = wire.SampleBuffer.parse(p[16:], wire.MEDIA_SOUND)
            except (ValueError, IndexError, struct.error):
                return
            self.stats["audio"] += 1
            local = self._audio_clock.now() if self._audio_clock else wire.CMTime()
            if self._audio_start is None:
                self._audio_start = (buf.pts, local)
            self._audio_last = (buf.pts, local)
            self.on_audio(buf)
        elif sub == wire.RELS:
            self._released.set()
        # SPRP / TJMP / SRAT / TBAS are informational.

    def _skew(self) -> float:
        """Device audio sample rate measured against our host clock (Hz)."""
        if not self._audio_start or not self._audio_last:
            return 48000.0
        (dev0, loc0), (dev1, loc1) = self._audio_start, self._audio_last
        local_ns = loc1.value - loc0.value
        device_ticks = dev1.value - dev0.value
        if local_ns <= 0 or device_ticks <= 0:
            return float(dev0.scale or 48000)
        scale = dev0.scale or 48000
        return scale * (local_ns / 1e9) / (device_ticks / scale)

