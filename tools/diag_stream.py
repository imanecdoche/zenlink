"""Stream statistics for one session: frames, keyframes, sizes, pacing."""
import logging, statistics, sys, threading, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from phonelink.cast import usb_session
from phonelink.cast.manager import _is_keyframe

logging.basicConfig(level=logging.INFO, format="%(relativeCreated)7.0f %(message)s")
logging.getLogger("phonelink.cast.usbmux").setLevel(logging.INFO)
secs = float(sys.argv[1]) if len(sys.argv) > 1 else 12
st = {"v": 0, "k": 0, "sizes": [], "fmt": [], "t": [], "a": 0}
def on_video(b):
    if b.format: st["fmt"].append((b.format.width, b.format.height, b.format.codec_string))
    if not b.data: return
    st["v"] += 1; st["sizes"].append(len(b.data)); st["t"].append(time.time())
    if _is_keyframe(b.data): st["k"] += 1
def on_audio(b): st["a"] += 1
d = usb_session.list_devices()[0]
s = usb_session.UsbCastSession(d.serial, on_video, on_audio, on_state=lambda p, x: print("STATE", p))
t = threading.Thread(target=s.run, daemon=True); t.start(); time.sleep(secs); s.stop(); t.join(8)
gaps = [b - a for a, b in zip(st["t"], st["t"][1:])] or [0]
print("formats:", st["fmt"][:3], "count", len(st["fmt"]))
print("frames:", st["v"], "keyframes:", st["k"], "audio packets:", st["a"])
if st["sizes"]:
    print("avg KB:", round(statistics.mean(st["sizes"]) / 1024, 1), "max KB:", round(max(st["sizes"]) / 1024, 1),
          "Mbps:", round(sum(st["sizes"]) * 8 / secs / 1e6, 1))
print("gap ms avg/max:", round(statistics.mean(gaps) * 1000, 1), round(max(gaps) * 1000, 1))
