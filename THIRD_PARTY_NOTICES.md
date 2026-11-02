# Third-party notices

PhoneLink uses or derives from the components below. Each remains under its
own license.

## quicktime_video_hack (MIT)

`phonelink/cast/wire.py` and `phonelink/cast/usb_session.py` implement Apple's
USB screen-capture protocol in Python following the protocol reverse
engineering published in https://github.com/danielpaulus/quicktime_video_hack.

```
MIT License

Copyright (c) 2019 danielpaulus

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Python packages (installed by Start.bat, not bundled in this repository)

| Package | License | Use |
|---|---|---|
| pyusb | BSD-3-Clause | USB access |
| libusb-package (libusb-1.0) | LGPL-2.1 (libusb), MIT (package) | USB backend fallback |
| aiohttp | Apache-2.0 | Local HTTP/WebSocket server |
| pywebview | BSD-3-Clause | Desktop window (Microsoft Edge WebView2) |

## System components (not distributed)

- libusb-win32 (`libusb0.sys`, `libusb0.dll`), LGPL/GPL, used as an installed
  filter driver when present on the PC.
- Apple Mobile Device USB driver, from Apple Devices or iTunes.
