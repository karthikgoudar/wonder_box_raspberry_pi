#!/bin/bash
# One-time setup on the Pi: start WonderBox when the desktop starts, and add
# the desktop icon. Run from anywhere: ~/Wonder-Box/tools/install_autostart.sh
set -e
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"

entry() {
cat <<DESKTOP
[Desktop Entry]
Type=Application
Name=WonderBox
Comment=AI sticker printer
Exec=$APP_DIR/run_wonderbox.sh
Icon=applications-graphics
Terminal=false
DESKTOP
}

mkdir -p "$HOME/.config/autostart" "$HOME/Desktop"
entry > "$HOME/.config/autostart/wonderbox.desktop"
entry > "$HOME/Desktop/WonderBox.desktop"
chmod +x "$APP_DIR/run_wonderbox.sh" "$HOME/Desktop/WonderBox.desktop"
echo "WonderBox will start at login: $HOME/.config/autostart/wonderbox.desktop"
echo "Desktop icon: $HOME/Desktop/WonderBox.desktop"
echo "To stop starting at login: rm $HOME/.config/autostart/wonderbox.desktop"
