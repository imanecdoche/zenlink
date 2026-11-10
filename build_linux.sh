#!/usr/bin/env bash
# ZenLink Linux Build & Package Script
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
cd "$HERE"

echo "=== 1. Building zlaac.so ==="
bash "$HERE/native/zlaac/build_zlaac_linux.sh" "$HERE/zenlink"

echo "=== 2. Building ZenLink Rust Native App (Release) ==="
if ! command -v cargo &> /dev/null && [ -f "$HOME/.cargo/env" ]; then
    . "$HOME/.cargo/env"
fi
export PKG_CONFIG_PATH="${HOME}/.local/lib/pkgconfig:${PKG_CONFIG_PATH:-}"
export LIBRARY_PATH="${HOME}/.local/lib:${LIBRARY_PATH:-}"

cd "$HERE/rust"
cargo build --release -p zenlink-app

echo "=== 3. Packaging Linux Distribution ==="
DIST="$HERE/dist/zenlink-linux-x86_64"
rm -rf "$DIST"
mkdir -p "$DIST/bin" "$DIST/share/applications" "$DIST/share/pixmaps"

# Binary
cp "$HERE/rust/target/release/ZenLink" "$DIST/bin/zenlink-native"

# Python Backend
cp -r "$HERE/zenlink" "$DIST/bin/zenlink-py"
cp "$HERE/pyproject.toml" "$HERE/requirements.txt" "$DIST/bin/"

# Desktop Entry & Icons
cp "$HERE/packaging/zenlink.desktop" "$DIST/share/applications/"
if [ -f "$HERE/assets/icon.png" ]; then
    cp "$HERE/assets/icon.png" "$DIST/share/pixmaps/zenlink.png"
elif [ -f "$HERE/ui/logo-256.png" ]; then
    cp "$HERE/ui/logo-256.png" "$DIST/share/pixmaps/zenlink.png"
fi

# ZenLinkService Sidecar Script
cat << 'EOF' > "$DIST/bin/ZenLinkService"
#!/usr/bin/env bash
DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
export PYTHONPATH="$DIR/zenlink-py:${PYTHONPATH:-}"
if [ -f "$DIR/../.venv/bin/python" ]; then
    exec "$DIR/../.venv/bin/python" -m zenlink "$@"
elif [ -f "$DIR/.venv/bin/python" ]; then
    exec "$DIR/.venv/bin/python" -m zenlink "$@"
else
    exec python3 -m zenlink "$@"
fi
EOF

# Launcher Script (bin/zenlink)
cat << 'EOF' > "$DIST/bin/zenlink"
#!/usr/bin/env bash
DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
export PYTHONPATH="$DIR/zenlink-py:${PYTHONPATH:-}"
export ZENLINK_SIDECAR="$DIR/ZenLinkService"
exec "$DIR/zenlink-native" "$@"
EOF

# Top-level Run Script
cat << 'EOF' > "$DIST/start.sh"
#!/usr/bin/env bash
HERE="$(cd "$(dirname "$0")" && pwd)"
exec "$HERE/bin/zenlink" "$@"
EOF

# README
cat << 'EOF' > "$DIST/README.md"
# ZenLink v2.5.1 for Linux (x86_64)

Satu jendela untuk mirroring dan kontrol perangkat iOS dan Android di PC Linux.

## Kebutuhan Sistem (Prerequisites)
Pastikan dependensi runtime berikut sudah terinstal di sistem Linux Anda:
```bash
# Ubuntu / Debian / Linux Mint
sudo apt update
sudo apt install -y adb ffmpeg python3 python3-pip

# Arch Linux
sudo pacman -S android-tools ffmpeg python
```

Install dependensi Python (opsional jika menggunakan venv, atau sistem global):
```bash
pip install -r bin/requirements.txt
```

## Cara Menjalankan
Cukup jalankan script:
```bash
./start.sh
```
atau langsung:
```bash
./bin/zenlink
```
EOF

chmod +x "$DIST/bin/zenlink" "$DIST/bin/zenlink-native" "$DIST/bin/ZenLinkService" "$DIST/start.sh"

# Create release tarball
cd "$HERE/dist"
tar -czvf "zenlink-v2.5.1-linux-x86_64.tar.gz" "zenlink-linux-x86_64"
zip -r "zenlink-v2.5.1-linux-x86_64.zip" "zenlink-linux-x86_64"

echo "=== Build Complete! ==="
echo "Tarball created at: $HERE/dist/zenlink-v2.5.1-linux-x86_64.tar.gz"
echo "Zip created at:     $HERE/dist/zenlink-v2.5.1-linux-x86_64.zip"
