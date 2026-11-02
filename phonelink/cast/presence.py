"""Which iPhones/iPads are plugged in, read from Windows' device list.

No USB I/O happens here: presence comes from `pnputil /enum-devices
/connected` and the driver binding from the registry, so polling is safe
while another program (or a cast session) owns the device.
"""

from __future__ import annotations

import re
import subprocess
import winreg

_NO_WINDOW = 0x08000000
_INSTANCE = re.compile(r"^USB\\VID_05AC&PID_(12[0-9A-F]{2})\\([^&\\]+)$", re.IGNORECASE)


def _reg_value(key, name):
    try:
        return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None


def connected_devices() -> list[dict]:
    try:
        out = subprocess.run(
            ["pnputil", "/enum-devices", "/connected"],
            capture_output=True, text=True, timeout=10, creationflags=_NO_WINDOW,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    devices = []
    for line in out.splitlines():
        if ":" not in line:
            continue
        label, _, value = line.partition(":")
        if label.strip().lower() != "instance id":
            continue
        match = _INSTANCE.match(value.strip())
        if not match:
            continue
        instance = value.strip()
        service = desc = None
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, rf"SYSTEM\CurrentControlSet\Enum\{instance}") as key:
                service = _reg_value(key, "Service")
                desc = _reg_value(key, "FriendlyName") or _reg_value(key, "DeviceDesc")
        except OSError:
            pass
        desc = (desc or "").split(";")[-1]
        name = "iPad" if "ipad" in desc.lower() else "iPhone" if "iphone" in desc.lower() else "iOS device"
        devices.append({
            "id": match.group(2),
            "name": name,
            "driver": (service or "").lower(),
            "ready": (service or "").lower() == "libusb0",
        })
    return devices
