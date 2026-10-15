#!/usr/bin/env bash
# tahrim_shekan installer — single command, user-level, no root required.
set -eu

BIN_DIR="$HOME/.local/bin"
DATA_DIR="$HOME/.local/share/tahrim_shekan"
UNIT_DIR="$HOME/.config/systemd/user"

for dep in curl python3 ss; do
  command -v "$dep" >/dev/null || { echo "missing dependency: $dep"; exit 1; }
done

mkdir -p "$BIN_DIR" "$DATA_DIR" "$UNIT_DIR"
install -m 755 tahrim_shekan "$BIN_DIR/tahrim_shekan"
install -m 644 bridge.py "$DATA_DIR/bridge.py"

cat > "$UNIT_DIR/tahrim-bridge.service" <<EOF
[Unit]
Description=tahrim_shekan bridge (http://127.0.0.1:8888 -> socks5://127.0.0.1:12334)
After=network-online.target

[Service]
ExecStart=/usr/bin/python3 $DATA_DIR/bridge.py
Restart=always
RestartSec=2

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now tahrim-bridge.service
loginctl enable-linger "$USER" 2>/dev/null || true

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "NOTE: add $BIN_DIR to PATH — run: echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.profile" ;;
esac

echo
echo "installed:"
echo "  $BIN_DIR/tahrim_shekan        main command"
echo "  $DATA_DIR/bridge.py           http->socks bridge (systemd user service)"
echo "  tahrim-bridge.service         enabled + lingering (survives reboot)"
echo
echo "prerequisite: a SOCKS5 proxy on 127.0.0.1:12334 (e.g. Hiddify)."
echo "verify with:  tahrim_shekan test"
