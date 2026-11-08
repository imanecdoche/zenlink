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
fi

# Launcher Script
cat << 'EOF' > "$DIST/bin/zenlink"
#!/usr/bin/env bash
DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
export PYTHONPATH="$DIR/zenlink-py:${PYTHONPATH:-}"
exec "$DIR/zenlink-native" "$@"
EOF
chmod +x "$DIST/bin/zenlink" "$DIST/bin/zenlink-native"

# Create release tarball
cd "$HERE/dist"
tar -czvf "zenlink-v2.5.1-linux-x86_64.tar.gz" "zenlink-linux-x86_64"

echo "=== Build Complete! ==="
echo "Tarball created at: $HERE/dist/zenlink-v2.5.1-linux-x86_64.tar.gz"
