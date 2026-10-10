#!/bin/sh
# Sets Vertorama up for your user, on any common desktop (no sudo):
#   - checks what Vertorama needs, and shows the install command if anything's missing
#   - Vertorama in your apps menu, with its icon
#   - Vertorama starts quietly at login, so the shortcut responds instantly
#   - Super+Shift+S starts a capture (Cinnamon, GNOME, Budgie, MATE, Xfce, KDE)
#
#   ./install-integration.sh            set it all up
#   ./install-integration.sh --remove   undo all of it
here=$(cd "$(dirname "$0")" && pwd)
if [ "$1" = "--remove" ]; then
  exec python3 "$here/tools/integrate.py" remove
fi
exec python3 "$here/tools/integrate.py" install
