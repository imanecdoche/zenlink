"""Replay the one sequence that once received a PING, step by step."""
import struct, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import libusb_package, usb.core, usb.util

be = libusb_package.get_libusb1_backend()
dev = usb.core.find(idVendor=0x05AC, backend=be)
print("cfg on device:", list(dev.ctrl_transfer(0x80, 0x08, 0, 0, 1)))
cfgs = {c.bConfigurationValue: [(i.bInterfaceNumber, hex(i.bInterfaceSubClass)) for i in c] for c in dev}
print("configs:", cfgs)
qt = next(v for v, ifs in cfgs.items() if any(s == "0x2a" for _, s in ifs))
mux = next(v for v, ifs in cfgs.items() if any(s == "0xfe" for _, s in ifs) and v != qt)
if "--from-mux" in sys.argv:
    dev.set_configuration(mux); time.sleep(1.0); print("went to mux cfg", mux)
dev.set_configuration(qt); time.sleep(1.0)
print("cfg on device:", list(dev.ctrl_transfer(0x80, 0x08, 0, 0, 1)))
cfg = dev.get_active_configuration()
iface = next(i for i in cfg if i.bInterfaceSubClass == 0x2A)
usb.util.claim_interface(dev, iface.bInterfaceNumber)
ein = [e for e in iface if e.bEndpointAddress & 0x80][0]; eout = [e for e in iface if not e.bEndpointAddress & 0x80][0]
for ep in (ein, eout):
    try: dev.clear_halt(ep)
    except usb.core.USBError as e: print("clear_halt", hex(ep.bEndpointAddress), e)
t0 = time.time(); got = None; pinged = False
while time.time() - t0 < 10:
    try:
        got = bytes(ein.read(1 << 20, timeout=500))
        if got: break
        print(round(time.time() - t0, 2), "zero-length packet")
    except usb.core.USBError as e:
        if "timeout" not in str(e).lower() and not isinstance(e, usb.core.USBTimeoutError): print("read err", e); break
        if not pinged and "--ping" in sys.argv:
            try: eout.write(struct.pack("<IIQ", 16, 0x70696E67, 0x0000000100000001), timeout=200); pinged = True; print("active ping sent")
            except usb.core.USBError as e: print("ping write:", e)
print("first read:", got[:24].hex() if got else None, "after", round(time.time() - t0, 1), "s")
usb.util.release_interface(dev, iface.bInterfaceNumber)
