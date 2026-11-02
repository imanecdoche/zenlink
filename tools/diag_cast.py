"""Diagnostics: run one cast session for N seconds with protocol logging."""
import logging, sys, threading, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from phonelink.cast import usb_session

logging.basicConfig(level=logging.DEBUG, format="%(relativeCreated)7.0f %(name)s %(message)s")
logging.getLogger("usb").setLevel(logging.WARNING)
secs = float(sys.argv[1]) if len(sys.argv) > 1 else 15
if "--no-trust" in sys.argv:
    usb_session.UsbCastSession._open_trust = lambda self, dev, cfg: None
devs = usb_session.list_devices()
print("devices:", [d.product for d in devs])
stats = {"v": 0, "a": 0}
s = usb_session.UsbCastSession(devs[0].serial, lambda b: stats.__setitem__("v", stats["v"] + 1),
                               lambda b: stats.__setitem__("a", stats["a"] + 1),
                               on_state=lambda p, d: print("STATE", p, d))
def run():
    try: s.run()
    except Exception as e: print("RUN ERROR:", e)
t = threading.Thread(target=run, daemon=True); t.start()
time.sleep(secs); s.stop(); t.join(8)
print("frames video/audio:", stats, "bytes:", s.stats)
