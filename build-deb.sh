#!/usr/bin/env bash
# motivnavi-screentweaks の .deb を ./dist/motivnavi-screentweaks.deb に作成する
set -euo pipefail

cd "$(dirname "$0")"

PKG=motivnavi-screentweaks
VERSION="$(tr -d '[:space:]' < VERSION)"
OUT_DIR="dist"
OUT="$OUT_DIR/$PKG.deb"

# 作業ディレクトリは権限を正しく扱えるよう /tmp 側に作る
BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT
ROOT="$BUILD/root"

install -d "$ROOT/DEBIAN" \
           "$ROOT/usr/bin" \
           "$ROOT/usr/lib/$PKG/web" \
           "$ROOT/usr/share/applications" \
           "$ROOT/usr/share/icons/hicolor/scalable/apps" \
           "$ROOT/usr/share/doc/$PKG"

install -m 0755 packaging/$PKG                 "$ROOT/usr/bin/$PKG"
install -m 0755 app/main.py                    "$ROOT/usr/lib/$PKG/main.py"
install -m 0644 app/powerdevil.py              "$ROOT/usr/lib/$PKG/powerdevil.py"
install -m 0644 app/web/index.html app/web/style.css app/web/app.js "$ROOT/usr/lib/$PKG/web/"
install -m 0644 packaging/$PKG.desktop         "$ROOT/usr/share/applications/$PKG.desktop"
install -m 0644 packaging/$PKG.svg             "$ROOT/usr/share/icons/hicolor/scalable/apps/$PKG.svg"
install -m 0644 README.md                      "$ROOT/usr/share/doc/$PKG/README.md"

# 改行コードが CRLF になっていた場合に備えて LF にそろえる
find "$ROOT/usr" -type f \( -name '*.py' -o -name '*.html' -o -name '*.css' -o -name '*.js' \
     -o -name '*.desktop' -o -name '*.svg' -o -name '*.md' -o -path "*/usr/bin/$PKG" \) \
     -exec sed -i 's/\r$//' {} +

INSTALLED_SIZE="$(du -sk "$ROOT/usr" | cut -f1)"

cat > "$ROOT/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Installed-Size: $INSTALLED_SIZE
Depends: python3 (>= 3.8)
Recommends: python3-pyqt6.qtwebengine | python3-webview | python3-pyqt5.qtwebengine, dbus-bin | qdbus-qt6
Maintainer: Enoki Denki <https://enoki.xyz>
Homepage: https://motivnavi.enoki.xyz
Description: Motivnavi OS screen timeout switcher
 Switches KDE PowerDevil screen dimming and sleep timeouts between
 "PC mode" and "car navigation mode" by editing ~/.config/powerdevilrc.
EOF

mkdir -p "$OUT_DIR"
dpkg-deb --root-owner-group --build "$ROOT" "$BUILD/$PKG.deb" >/dev/null
cp -f "$BUILD/$PKG.deb" "$OUT"

echo "作成しました: $OUT (version $VERSION)"
