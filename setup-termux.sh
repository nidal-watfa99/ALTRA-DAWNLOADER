#!/data/data/com.termux/files/usr/bin/bash
# ALTRA Helper: إعداد تلقائي على أندرويد (Termux)
set -e
BASE="${ALTRA_BASE:-https://nidal-watfa99.github.io}"

echo "▶ تثبيت الحزم (python, ffmpeg, nodejs)…"
pkg update -y
pkg install -y python ffmpeg nodejs curl termux-api unzip
[ -d "$HOME/storage/shared" ] || { echo "▶ اسمح بالوصول للتخزين (اضغط سماح) ليظهر التحميل في المعرض…"; termux-setup-storage; sleep 5; }

echo "▶ تثبيت yt-dlp…"
python -m pip install -U "yt-dlp[default]" || python -m pip install -U yt-dlp

mkdir -p "$HOME/altra"
cd "$HOME/altra"
ZIP=$(ls -t "$HOME"/storage/downloads/ALTRA-DAWNLOADER*.zip 2>/dev/null | head -1)
if [ -n "$ZIP" ]; then
  echo "▶ تثبيت الملفات من الأرشيف المحلي: $(basename "$ZIP")"
  rm -rf "$TMPDIR/altra-src" && mkdir -p "$TMPDIR/altra-src" && unzip -oq "$ZIP" -d "$TMPDIR/altra-src"
  cp -f "$TMPDIR"/altra-src/*/altra-server.py "$TMPDIR"/altra-src/*/index.html "$TMPDIR"/altra-src/*/sw.js \
        "$TMPDIR"/altra-src/*/manifest.webmanifest "$TMPDIR"/altra-src/*/icon-*.png .
else
  echo "▶ تنزيل ملفات ALTRA من GitHub…"
  for f in altra-server.py index.html sw.js manifest.webmanifest icon-192.png icon-512.png; do
    curl -fsSL -o "$f" "$BASE/$f" && echo "   ✓ $f"
  done
fi
echo "   النسخة المثبتة: $(grep -m1 '^VERSION' altra-server.py)"

sed -i "/alias altra=/d" "$HOME/.bashrc" 2>/dev/null || true
echo "alias altra='cd \$HOME/altra && python altra-server.py --update'" >> "$HOME/.bashrc"
command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock || true

echo
echo "✅ جاهز. في المرات القادمة اكتب فقط:  altra"
echo "   ثم افتح ALTRA أو http://localhost:8787"
echo
exec python altra-server.py
