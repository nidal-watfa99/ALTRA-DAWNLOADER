#!/data/data/com.termux/files/usr/bin/bash
# ALTRA Helper: إعداد تلقائي على أندرويد (Termux)
set -e

# مصادر التنزيل بالترتيب (يمكن تحديد مصدر أول عبر ALTRA_BASE)
BASES=()
[ -n "$ALTRA_BASE" ] && BASES+=("${ALTRA_BASE%/}")
BASES+=(
  "https://nidal-watfa99.github.io/ALTRA-DAWNLOADER"
  "https://nidal-watfa99.github.io"
  "https://raw.githubusercontent.com/nidal-watfa99/ALTRA-DAWNLOADER/main"
  "https://raw.githubusercontent.com/nidal-watfa99/nidal-watfa99.github.io/main"
)

echo "▶ تثبيت الحزم (python, ffmpeg, nodejs)…"
pkg update -y
pkg install -y python ffmpeg nodejs curl termux-api unzip
[ -d "$HOME/storage/shared" ] || { echo "▶ اسمح بالوصول للتخزين (اضغط سماح) ليظهر التحميل في المعرض…"; termux-setup-storage; sleep 5; }

echo "▶ تثبيت yt-dlp…"
python -m pip install -U "yt-dlp[default]" || python -m pip install -U yt-dlp

mkdir -p "$HOME/altra"
cd "$HOME/altra"

# يتحقق أن الملف المنزَّل سليم (وليس صفحة خطأ HTML)
fetch_one() {  # $1=file
  local f="$1" b tmp="$1.part"
  for b in "${BASES[@]}"; do
    if curl -fsSL --connect-timeout 10 --max-time 120 -o "$tmp" "$b/$f" 2>/dev/null; then
      case "$f" in
        altra-server.py) grep -q '^VERSION' "$tmp" || { rm -f "$tmp"; continue; } ;;
        index.html)      grep -qi '<html' "$tmp"     || { rm -f "$tmp"; continue; } ;;
        sw.js)           grep -q 'addEventListener' "$tmp" || { rm -f "$tmp"; continue; } ;;
      esac
      mv -f "$tmp" "$f"; echo "   ✓ $f  ← $b"; return 0
    fi
    rm -f "$tmp"
  done
  return 1
}

echo "▶ تنزيل ملفات ALTRA (الأحدث من الشبكة أولاً)…"
OK=1
for f in altra-server.py index.html sw.js manifest.webmanifest icon-192.png icon-512.png; do
  if ! fetch_one "$f"; then
    echo "   ✗ تعذّر تنزيل $f"
    case "$f" in altra-server.py|index.html) OK=0 ;; esac
  fi
done

if [ "$OK" -ne 1 ]; then
  # بديل: أرشيف محلي في التنزيلات (قد يكون أقدم من النسخة المنشورة)
  ZIP=$(ls -t "$HOME"/storage/downloads/ALTRA-DAWNLOADER*.zip 2>/dev/null | head -1)
  if [ -n "$ZIP" ]; then
    T="${TMPDIR:-$PREFIX/tmp}/altra-src"
    echo "▶ لا اتصال بالمصادر. تثبيت من الأرشيف المحلي: $(basename "$ZIP")"
    rm -rf "$T" && mkdir -p "$T" && unzip -oq "$ZIP" -d "$T"
    cp -f "$T"/*/altra-server.py "$T"/*/index.html "$T"/*/sw.js "$T"/*/manifest.webmanifest "$T"/*/icon-*.png . 2>/dev/null || \
    cp -f "$T"/altra-server.py "$T"/index.html "$T"/sw.js "$T"/manifest.webmanifest "$T"/icon-*.png .
  fi
fi

if [ ! -s altra-server.py ]; then
  echo "❌ لم يتم الحصول على altra-server.py. تحقق من الإنترنت ثم أعد تشغيل الأمر،"
  echo "   أو نزّل ALTRA-DAWNLOADER.zip إلى مجلد التنزيلات وأعد التشغيل."
  exit 1
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
