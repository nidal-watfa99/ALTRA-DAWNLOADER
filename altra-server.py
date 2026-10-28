#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ALTRA Helper  ·  المساعد المحلي لتطبيق ALTRA-DAWNLOADER

يشغّل yt-dlp على جهازك ويقدّم للتطبيق واجهة صغيرة (HTTP) لتحميل الفيديو والصوت
من أكثر من ألف موقع (يوتيوب، إنستغرام، تيك توك، فيسبوك، X، ريديت، ...).
كما يقدّم ملفات التطبيق نفسه، فيمكن فتح  http://localhost:8787  وتثبيته مباشرة.

التشغيل:
    python altra-server.py                 # المنفذ 8787، على هذا الجهاز فقط
    python altra-server.py --port 9000
    python altra-server.py --host 0.0.0.0  # للسماح لأجهزة الشبكة المحلية
    python altra-server.py --cookies cookies.txt

المتطلبات:  Python 3.8+  و  yt-dlp  (pip install -U "yt-dlp[default]")  و  ffmpeg (اختياري، للدمج والتحويل)
"""
import argparse
import collections
import glob
import json
import mimetypes
import os
import platform
import re
import shutil
import signal
import sys
import tempfile
import threading
import time
import traceback
import uuid
import subprocess
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

VERSION = "8.8"
HERE = os.path.realpath(os.path.dirname(os.path.abspath(__file__)))

DASHBOARD_HTML = r'''<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ALTRA Helper · لوحة التحكم</title>
<style>
:root{--bg:#05080d;--card:#0c1219;--border:#1a2533;--c:#00d2ff;--g:#00ff88;--r:#ff4757;--y:#ffc107;--t:#e8f0f8;--m:#8ba3b8}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--t);min-height:100vh;padding:16px}
h1{font-size:1.4rem;color:var(--c);margin-bottom:4px}
.sub{color:var(--m);font-size:.85rem;margin-bottom:20px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:20px}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:14px 16px}
.card .label{font-size:.75rem;color:var(--m);margin-bottom:4px}
.card .val{font-size:1.3rem;font-weight:700;color:var(--c)}
.card .val.g{color:var(--g)}.card .val.r{color:var(--r)}.card .val.y{color:var(--y)}
.actions{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:20px}
button{background:#0e1a24;border:1px solid var(--border);color:var(--t);padding:8px 14px;border-radius:8px;cursor:pointer;font-size:.85rem;transition:.15s}
button:hover{border-color:var(--c);color:var(--c)}
button.danger{border-color:#5a2020;color:#ff8a8a}button.danger:hover{background:#2a1010}
button.good{border-color:#1a4a30;color:var(--g)}button.good:hover{background:#0a2a18}
table{width:100%;border-collapse:collapse;font-size:.82rem}
th,td{padding:8px 10px;text-align:right;border-bottom:1px solid var(--border)}
th{color:var(--m);font-weight:600;position:sticky;top:0;background:var(--card)}
tr:hover{background:#0f1820}
.badge{display:inline-block;padding:2px 8px;border-radius:99px;font-size:.72rem;font-weight:600}
.b-queued{background:#1a2a3a;color:#7ab} .b-running{background:#1a3a2a;color:var(--g)}
.b-done{background:#0a2a1a;color:#6f6} .b-error{background:#3a1515;color:#f88}
.b-cancelled{background:#2a2a1a;color:#cc8}
.prog{height:4px;background:#1a2533;border-radius:99px;overflow:hidden;min-width:60px}
.prog>i{display:block;height:100%;background:linear-gradient(90deg,var(--c),var(--g));border-radius:99px}
.empty{text-align:center;padding:40px;color:var(--m)}
.toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:#1a2a3a;border:1px solid var(--c);padding:10px 20px;border-radius:10px;opacity:0;transition:.3s;pointer-events:none;z-index:99}
.toast.show{opacity:1}
a{color:var(--c);text-decoration:none}
footer{margin-top:30px;text-align:center;color:var(--m);font-size:.75rem}
</style>
</head>
<body>
<h1>⚙️ ALTRA Helper · لوحة التحكم</h1>
<div class="sub">v''' + VERSION + r''' · المساعد المحلي · <a href="/">العودة للتطبيق</a></div>

<div class="grid" id="stats">
  <div class="card"><div class="label">الحالة</div><div class="val g" id="s-status">...</div></div>
  <div class="card"><div class="label">وقت التشغيل</div><div class="val" id="s-uptime">—</div></div>
  <div class="card"><div class="label">المهام النشطة</div><div class="val" id="s-active">0</div></div>
  <div class="card"><div class="label">إجمالي المهام</div><div class="val" id="s-total">0</div></div>
  <div class="card"><div class="label">حجم الكاش</div><div class="val" id="s-cache">—</div></div>
  <div class="card"><div class="label">yt-dlp</div><div class="val" id="s-ytdlp">—</div></div>
</div>

<div class="actions">
  <button class="good" onclick="refresh()">🔄 تحديث</button>
  <button onclick="clearFinished()">🧹 مسح المنتهية</button>
  <button class="danger" onclick="cancelAll()">⏹ إلغاء الكل</button>
  <button class="danger" onclick="clearCache()">🗑 تفريغ الكاش بالكامل</button>
</div>

<div class="card" style="overflow:auto;max-height:55vh">
<table>
<thead><tr>
  <th>الحالة</th><th>التقدم</th><th>العنوان / الرابط</th><th>الموقع</th><th>الحجم</th><th>السرعة</th><th></th>
</tr></thead>
<tbody id="jobs"></tbody>
</table>
<div class="empty" id="empty" style="display:none">لا توجد مهام حالياً</div>
</div>

<footer>ALTRA Helper Control Panel · التحديث التلقائي كل 3 ثوانٍ</footer>
<div class="toast" id="toast"></div>

<script>
const $ = s => document.querySelector(s);
const esc = s => String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function toast(m){const t=$('#toast');t.textContent=m;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2500)}
function fmtBytes(n){if(!n||n<0)return'—';const u=['B','KB','MB','GB'];let i=0;while(n>=1024&&i<3){n/=1024;i++}return n.toFixed(i?1:0)+' '+u[i]}
function fmtUp(s){const h=Math.floor(s/3600),m=Math.floor((s%3600)/60),sec=s%60;return(h?h+'س ':'')+(m?m+'د ':'')+sec+'ث'}
function badge(st){return'<span class="badge b-'+st+'">'+({queued:'في الانتظار',running:'جاري',paused:'متوقف مؤقتاً',done:'مكتمل',error:'خطأ',cancelled:'ملغى'}[st]||st)+'</span>'}
async function refresh(){
  try{
    const [info,jobsRes]=await Promise.all([fetch('/api/info').then(r=>r.json()),fetch('/api/jobs').then(r=>r.json())]);
    $('#s-status').textContent='متصل';$('#s-status').className='val g';
    $('#s-uptime').textContent=fmtUp(info.uptime||0);
    const st=info.jobs_by_state||{};
    const active=(st.queued||0)+(st.running||0);
    $('#s-active').textContent=active;
    $('#s-active').className=active?'val y':'val';
    $('#s-total').textContent=info.jobs_total||0;
    $('#s-cache').textContent=fmtBytes(info.cache_size)+(info.cache_files?' ('+info.cache_files+')':'');
    $('#s-ytdlp').textContent=info.ytdlp||'غير مثبّت';
    $('#s-ytdlp').className=info.ytdlp?'val g':'val r';
    const jobs=jobsRes.jobs||[];
    const tb=$('#jobs');tb.innerHTML='';
    $('#empty').style.display=jobs.length?'none':'block';
    for(const j of jobs){
      const tr=document.createElement('tr');
      const title=(j.title||j.url||'').slice(0,60);
      tr.innerHTML=`
        <td>${badge(j.state)}</td>
        <td><div class="prog"><i style="width:${j.progress||0}%"></i></div> ${Math.round(j.progress||0)}%</td>
        <td title="${esc(j.url)}">${esc(title)}${(j.error?' <small style="color:#f88">'+esc(j.error.slice(0,40))+'</small>':'')}</td>
        <td>${esc(j.site)||'—'}</td>
        <td>${fmtBytes(j.size||j.bytes)}</td>
        <td>${j.speed?fmtBytes(j.speed)+'/s':'—'}</td>
        <td>${['queued','running','paused'].includes(j.state)?`<button onclick="cancel('${esc(j.id)}')">إلغاء</button>`:''}
            ${j.state==='done'?`<a href="/file/${esc(j.id)}" download>تحميل</a>`:''}</td>`;
      tb.appendChild(tr);
    }
  }catch(e){$('#s-status').textContent='خطأ';$('#s-status').className='val r';toast('فشل التحديث: '+e.message)}
}
async function cancel(id){await fetch('/api/cancel/'+id,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});toast('تم الإلغاء');refresh()}
async function cancelAll(){if(!confirm('إلغاء كل المهام الجارية؟'))return;const r=await fetch('/api/cancel-all',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).then(x=>x.json());toast('أُلغي '+r.cancelled);refresh()}
async function clearFinished(){const r=await fetch('/api/jobs/clear',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).then(x=>x.json());toast('تم مسح '+r.removed+' مهمة');refresh()}
async function clearCache(){if(!confirm('تفريغ الكاش بالكامل وحذف كل المهام؟'))return;await fetch('/api/cache/clear',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});toast('تم تفريغ الكاش');refresh()}
refresh();setInterval(refresh,3000);
</script>
</body>
</html>
'''

# ── yt-dlp: مثبّت عبر pip، أو ملف yt-dlp (zipapp) بجوار هذا الملف ──────────────
yt_dlp = None
try:
    import yt_dlp  # type: ignore
except ImportError:
    for cand in (os.environ.get("YTDLP_PATH", ""), os.path.join(HERE, "yt-dlp")):
        if cand and os.path.isfile(cand):
            sys.path.insert(0, cand)
            try:
                import yt_dlp  # type: ignore
                break
            except ImportError:
                sys.path.remove(cand)

AUDIO_FORMATS = {"mp3", "m4a", "aac", "flac", "wav", "ogg", "opus", "alac"}
VIDEO_FORMATS = {"mp4", "mkv", "webm", "mov", "avi", "flv", "gif", "best"}
# صيغ تُدمج مباشرة، وأخرى تُحوَّل بعد التحميل عبر ffmpeg
MERGE_FORMATS = {"mp4", "mkv", "webm"}
CONVERT_FORMATS = {"mov", "avi", "flv", "gif"}
STATIC_OK = {".html", ".js", ".webmanifest", ".png", ".json", ".css", ".svg", ".ico"}
# المواقع المسموح لها افتراضياً بالاتصال بالمساعد (يمكن إضافة المزيد بـ --origin)
DEFAULT_ORIGINS = {"https://nidal-watfa99.github.io", "https://danial56hd-wq.github.io"}
# حدود السرعة المسموحة (للخيار «حد السرعة» في التطبيق) → بايت/ثانية
RATE_LIMITS = {"250K": 250 * 1024, "500K": 500 * 1024, "1M": 1024 * 1024, "2M": 2 * 1024 * 1024, "5M": 5 * 1024 * 1024}
MEDIA_EXTS = {".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi", ".flv", ".gif", ".3gp",
              ".mp3", ".m4a", ".aac", ".flac", ".wav", ".ogg", ".opus", ".alac", ".weba", ".mka", ".zip"}
LIB = {}          # معرّف ← مسار ملف في «ملفاتي»
LIB_LOCK = threading.Lock()

CFG = {
    "cache": os.path.join(tempfile.gettempdir(), "altra-cache"),
    "cookies": None,
    "browser": None,
    "keep": 60,
    "origins": set(DEFAULT_ORIGINS),
    "allow_all": False,
    "loopback": True,
    "has_ffmpeg": bool(shutil.which("ffmpeg")),
    "save": None,
    "gallery": False,
}
JOBS = {}
JOBS_LOCK = threading.Lock()
SLOTS = threading.BoundedSemaphore(10)
START_TIME = time.time()


class Cancelled(Exception):
    pass


# ── سجل الأحداث والأخطاء (يقرأه التطبيق من /api/log) ──
LOG = collections.deque(maxlen=800)
LOG_N = [0]
LOG_LOCK = threading.Lock()


def slog(msg, lvl="info", job=None):
    tag = ("[" + job.id[:6] + "] ") if job is not None else ""
    with LOG_LOCK:
        LOG_N[0] += 1
        LOG.append({"n": LOG_N[0], "t": time.strftime("%H:%M:%S"), "lvl": lvl, "msg": (tag + str(msg))[:6000]})
    try:
        print((" [" + lvl + "] " + tag + str(msg))[:300], flush=True)
    except Exception:  # noqa: BLE001
        pass


class YLog:
    """يلتقط رسائل yt-dlp المهمة (تحذيرات وأخطاء وخطوات الدمج) في السجل."""
    KEEP = ("[info]", "[Merger]", "[ExtractAudio]", "[VideoRemuxer]", "[ffmpeg]", "[download] Destination",
            "[Instagram]", "[instagram]", "[Fixup")

    def __init__(self, job):
        self.job = job

    def debug(self, m):
        m = str(m)
        if m.startswith(self.KEEP):
            slog("yt-dlp: " + m, "info", self.job)

    info = debug

    def warning(self, m):
        slog("yt-dlp ⚠ " + str(m), "warn", self.job)

    def error(self, m):
        slog("yt-dlp ✗ " + str(m), "error", self.job)


class Job:
    def __init__(self, url, params):
        self.id = uuid.uuid4().hex[:16]
        self.url = url
        self.params = params
        self.state = "queued"       # queued | running | done | error | cancelled
        self.phase = "queued"
        self.progress = 0.0
        self.speed = 0
        self.eta = None
        self.bytes = 0
        self.base_bytes = 0
        self.title = ""
        self.filename = ""
        self.filepath = ""
        self.size = 0
        self.error = ""
        self.hint = ""
        self.login = False
        self.saved = ""
        self.gallery = False
        self.save_error = ""
        self.site = site_of(url)
        self.created = time.time()
        self.finished = None
        self.cancel = threading.Event()
        self.dir = os.path.join(CFG["cache"], self.id)
        self.pausing = False        # طُلب الإيقاف المؤقت (يُحتفظ بالملف الجزئي)
        self.resumed = False        # استُؤنفت المهمة بعد إيقاف
        self.thumbnail = ""
        self.duration = None
        self.uploader = ""

    def public(self):
        return {
            "thumbnail": self.thumbnail, "duration": self.duration, "uploader": self.uploader,
            "id": self.id, "state": self.state, "phase": self.phase,
            "progress": round(self.progress, 1), "speed": self.speed or 0,
            "eta": self.eta, "bytes": self.bytes, "title": self.title,
            "filename": self.filename, "size": self.size,
            "error": self.error, "hint": self.hint,
            "login": self.login, "site": self.site,
            "saved": self.saved, "gallery": self.gallery, "save_error": self.save_error,
            "url": self.url, "created": self.created, "finished": self.finished,
        }


# ── مساعدات ────────────────────────────────────────────────────────────────
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def clean_error(msg):
    msg = ANSI.sub("", str(msg)).strip()
    msg = re.sub(r"^(ERROR:\s*)+", "", msg)
    return msg[:400]


def site_of(url):
    try:
        h = (urlparse(url).hostname or "").lower()
    except Exception:
        return ""
    for exact, name in (("x.com", "x"), ("twitter.com", "x"), ("vk.com", "vk"), ("ok.ru", "ok")):
        if h == exact or h.endswith("." + exact):
            return name
    for key, name in (
        ("instagram", "instagram"), ("facebook", "facebook"), ("fb.watch", "facebook"),
        ("youtube", "youtube"), ("youtu.be", "youtube"), ("tiktok", "tiktok"),
        ("reddit", "reddit"),
        ("soundcloud", "soundcloud"), ("vimeo", "vimeo"), ("dailymotion", "dailymotion"),
        ("twitch", "twitch"), ("bilibili", "bilibili"), ("pinterest", "pinterest"),
        ("snapchat", "snapchat"), ("tumblr", "tumblr"),
    ):
        if key in h:
            return name
    return h


LOGIN_KEYS = ("login required", "sign in", "log in", "logged in", "cookies", "rate-limit",
              "empty media response", "age-restricted", "confirm you", "authentication",
              "checkpoint", "you must be", "restricted video", "private video")


NOT_LOGIN_KEYS = ("unsupported url", "name or service not known", "timed out", "urlopen error",
                  "temporary failure", "network is unreachable", "connection refused",
                  "ffmpeg", "ffprobe", "no space left", "cancel")
LOGIN_SITES = ("instagram", "facebook", "x", "tiktok")


def login_needed(msg, url):
    m = msg.lower()
    if any(k in m for k in NOT_LOGIN_KEYS):
        return False
    if any(k in m for k in LOGIN_KEYS):
        return True
    # في إنستغرام وفيسبوك وX وتيك توك أغلب حالات الفشل سببها أن المقطع يتطلب حساباً
    return site_of(url) in LOGIN_SITES


def explain(msg):
    m = msg.lower()
    if any(k in m for k in LOGIN_KEYS):
        return "هذا المحتوى يتطلب تسجيل الدخول. اضغط الشارة الزرقاء في التطبيق لاستيراد جلسة الدخول."
    if "unsupported url" in m:
        return "الرابط غير مدعوم أو لا يحتوي على فيديو."
    if "private" in m:
        return "المحتوى خاص."
    if any(k in m for k in ("name or service not known", "timed out", "urlopen error",
                            "temporary failure", "network is unreachable", "connection")):
        return "تعذّر الوصول إلى الموقع من هذا الجهاز. تحقق من الإنترنت أو شغّل VPN."
    if "http error 403" in m or "http error 429" in m:
        return "الموقع رفض الطلب مؤقتاً. حدّث yt-dlp (pip install -U yt-dlp) أو استخدم cookies.txt."
    if "ffmpeg" in m or "ffprobe" in m:
        return "ffmpeg غير مثبّت. ثبّته لدمج الفيديو والصوت وتحويل الصيغ."
    return ""


def build_opts(job, hook):
    p = job.params
    q = str(p.get("quality") or "max")
    fmt = str(p.get("format") or "mp4").lower()
    mode = str(p.get("mode") or "auto")
    h = int(q) if q.isdigit() else None
    ff = CFG["has_ffmpeg"]
    audio = mode == "audio" or fmt in AUDIO_FORMATS

    hf = f"[height<={h}]" if h else ""
    is_search = bool(re.match(r"^(ytsearch|ytsearchdate|youtube:search)\d*:", job.url or "", re.I))
    opts = {
        "outtmpl": os.path.join(job.dir, "%(title).120B [%(id)s].%(ext)s"),
        "noplaylist": not is_search,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": YLog(job),
        "progress_hooks": [hook],
        "retries": 5,
        "fragment_retries": 5,
        "socket_timeout": 30,
        "concurrent_fragment_downloads": 8,
        "windowsfilenames": True,
        "overwrites": True,
    }
    if is_search:
        opts["playlistend"] = 5  # safety limit for ytsearchN
    stages = 1
    if audio:
        opts["format"] = "bestaudio/best"
        if ff:
            codec = fmt if fmt in AUDIO_FORMATS else ("best" if fmt == "best" else "mp3")
            pp = {"key": "FFmpegExtractAudio", "preferredcodec": "vorbis" if codec == "ogg" else codec}
            if codec in ("mp3", "ogg", "opus"):
                pp["preferredquality"] = "320"
            opts["postprocessors"] = [pp]
    elif mode == "mute":
        opts["format"] = f"bv*{hf}[ext=mp4]/bv*{hf}/bv*/b"
    elif ff:
        if fmt == "webm":
            opts["format"] = (f"bv*{hf}[ext=webm]+ba[ext=webm]/bv*{hf}+ba/b{hf}/b")
            opts["merge_output_format"] = "webm"
        elif fmt == "mkv":
            opts["format"] = f"bv*{hf}+ba/b{hf}/b"
            opts["merge_output_format"] = "mkv"
        elif fmt == "best":
            # الأصل بلا أي تحويل: أفضل فيديو + أفضل صوت بحاويته الطبيعية
            opts["format"] = f"bv*{hf}+ba/b{hf}/b"
        elif fmt in CONVERT_FORMATS:
            opts["format"] = f"bv*{hf}+ba/b{hf}/b"
            opts["merge_output_format"] = "mkv"
            opts["postprocessors"] = [{"key": "FFmpegVideoConvertor", "preferedformat": fmt}]
        else:
            opts["format"] = (f"bv*{hf}[ext=mp4]+ba[ext=m4a]/bv*{hf}+ba/b{hf}[ext=mp4]/b{hf}/b")
            opts["merge_output_format"] = "mp4"
            opts["postprocessor_args"] = {"merger": ["-movflags", "+faststart"]}
        stages = 2
    else:
        opts["format"] = f"b{hf}[ext=mp4]/b{hf}/b[ext=mp4]/b"
        if fmt not in ("mp4", "best"):
            slog("ffmpeg غير موجود: لا يمكن التحويل إلى %s، سيُحفظ بصيغته الأصلية (ثبّت ffmpeg)" % fmt, "warn", job)

    # ── إضافات 8.8: حد السرعة · الاستئناف · الترجمة · الغلاف والوسوم ──
    lim = RATE_LIMITS.get(str(p.get("limit") or ""))
    if lim:
        opts["ratelimit"] = lim
    if job.resumed:
        opts["overwrites"] = None  # يكمل الملف الجزئي بدل البدء من الصفر
    if ff and p.get("tags") and audio and fmt != "wav":
        pps = opts.setdefault("postprocessors", [])
        pps.append({"key": "FFmpegMetadata", "add_metadata": True})
        if fmt in ("mp3", "m4a"):
            opts["writethumbnail"] = True
            pps.insert(0, {"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"})
            pps.append({"key": "EmbedThumbnail"})
    if ff and p.get("subs") and not audio and mode != "mute" and fmt in ("mp4", "mkv", "webm", "best"):
        opts["writesubtitles"] = True
        opts["subtitleslangs"] = ["ar", "en"]
        opts.setdefault("postprocessors", []).append({"key": "FFmpegEmbedSubtitle"})

    cookies = cookies_path()
    if os.path.isfile(cookies):
        opts["cookiefile"] = cookies
    elif CFG["browser"]:
        opts["cookiesfrombrowser"] = (CFG["browser"],)

    runtimes = {}
    for rt in ("deno", "node", "bun"):
        if shutil.which(rt):
            runtimes[rt] = {}
    if runtimes:
        opts["js_runtimes"] = runtimes
    return opts, stages


EXTRA_PP = {"FFmpegMetadata", "FFmpegThumbnailsConvertor", "EmbedThumbnail", "FFmpegEmbedSubtitle"}


def strip_extras(opts):
    """يزيل الترجمة والغلاف والوسوم (إضافات اختيارية) إن تسبّبت في فشل التحميل."""
    for k in ("writesubtitles", "subtitleslangs", "writethumbnail"):
        opts.pop(k, None)
    pps = [x for x in opts.get("postprocessors", []) if x.get("key") not in EXTRA_PP]
    if pps:
        opts["postprocessors"] = pps
    else:
        opts.pop("postprocessors", None)


def probe_opts():
    """خيارات yt-dlp للاستعلام فقط (بلا تحميل): نفس الكوكيز ومحرّكات JS المستخدمة في التحميل."""
    o = {"quiet": True, "no_warnings": True, "skip_download": True, "socket_timeout": 20,
         "retries": 2, "noplaylist": False}
    cookies = cookies_path()
    if os.path.isfile(cookies):
        o["cookiefile"] = cookies
    elif CFG["browser"]:
        o["cookiesfrombrowser"] = (CFG["browser"],)
    runtimes = {rt: {} for rt in ("deno", "node", "bun") if shutil.which(rt)}
    if runtimes:
        o["js_runtimes"] = runtimes
    return o


def probe(url, query=None, n=12, kind="video", source="yt"):
    """معاينة رابط: العنوان والصورة والمدة والجودات المتاحة بأحجامها التقريبية، أو عناصر قائمة تشغيل/نتائج بحث."""
    if yt_dlp is None:
        raise RuntimeError("yt-dlp غير مثبّت. نفّذ: pip install -U \"yt-dlp[default]\"")

    def ent(e):
        u = e.get("webpage_url") or e.get("url") or ""
        if u and not re.match(r"^https?://", u) and e.get("id") and (e.get("ie_key") or "").lower().startswith("youtube"):
            u = "https://www.youtube.com/watch?v=" + e["id"]
        th = e.get("thumbnail") or ""
        if not th:
            ts = e.get("thumbnails") or []
            th = (ts[-1].get("url") if ts else "") or ""
        if not th and e.get("id") and (e.get("ie_key") or "").lower().startswith("youtube"):
            th = "https://i.ytimg.com/vi/%s/mqdefault.jpg" % e["id"]
        is_list = bool(re.search(r"[?&]list=|/playlist\?|/sets/|/album/", u or "")) and "watch?v=" not in (u or "")
        return {"id": e.get("id"), "title": (e.get("title") or "")[:200], "url": u, "is_list": is_list,
                "duration": e.get("duration"), "thumbnail": th,
                "uploader": (e.get("uploader") or e.get("channel") or "")[:80]}

    o = probe_opts()
    if query:
        n = max(1, min(int(n), 200))
        if source == "sc":
            src = "scsearch%d:%s" % (n, query)
        elif kind == "playlist":
            # بحث يوتيوب مفلتر على «قوائم التشغيل» (ألبومات الفنانين وقوائمهم)
            from urllib.parse import quote_plus
            src = "https://www.youtube.com/results?search_query=%s&sp=EgIQAw%%3D%%3D" % quote_plus(query)
            o["playlistend"] = n
        else:
            src = "ytsearch%d:%s" % (n, query)
        o["extract_flat"] = "in_playlist"
        with yt_dlp.YoutubeDL(o) as ydl:
            info = ydl.extract_info(src, download=False)
        res = [x for x in (ent(e) for e in (info.get("entries") or []) if e) if x["url"]]
        if kind == "playlist":
            res = [x for x in res if x["is_list"]] or res
        return {"kind": "search", "title": query, "entries": res}

    o["extract_flat"] = "in_playlist"
    with yt_dlp.YoutubeDL(o) as ydl:
        info = ydl.extract_info(normalize_url(url), download=False)
    if not info:
        raise RuntimeError("لم يُعثر على وسائط في هذا الرابط.")
    if info.get("_type") == "playlist" or info.get("entries"):
        ents = [ent(e) for e in (info.get("entries") or []) if e]
        ents = [x for x in ents if x["url"]][:200]
        return {"kind": "playlist", "title": (info.get("title") or "")[:200], "uploader": (info.get("uploader") or info.get("channel") or "")[:80],
                "thumbnail": info.get("thumbnail") or (ents[0]["thumbnail"] if ents else ""), "entries": ents}

    # فيديو واحد: نحتاج قائمة الصيغ كاملة لحساب الأحجام
    if not info.get("formats"):
        o2 = probe_opts()
        o2["noplaylist"] = True
        with yt_dlp.YoutubeDL(o2) as ydl:
            info = ydl.extract_info(normalize_url(url), download=False)
    fmts = info.get("formats") or []
    best_audio = 0
    for f in fmts:
        if f.get("vcodec") in (None, "none") and f.get("acodec") not in (None, "none"):
            best_audio = max(best_audio, f.get("filesize") or f.get("filesize_approx") or 0)
    sizes = {}
    for f in fmts:
        h = f.get("height")
        if not h or f.get("vcodec") in (None, "none"):
            continue
        sz = f.get("filesize") or f.get("filesize_approx") or 0
        if f.get("acodec") in (None, "none"):
            sz = sz + best_audio if sz else 0
        if h not in sizes or (sz and sz > sizes[h]):
            sizes[h] = sz
    heights = sorted(sizes, reverse=True)
    one = ent(info)
    one.update({"kind": "video", "heights": heights, "sizes": {str(h): sizes[h] for h in heights},
                "audio_size": best_audio, "live": bool(info.get("is_live")),
                "thumbnail": info.get("thumbnail") or one["thumbnail"]})
    return one


def suggest(q):
    """اقتراحات بحث يوتيوب (يجلبها المساعد لأن المتصفح يمنعها بـ CORS)."""
    import urllib.request
    import urllib.parse
    u = "https://suggestqueries.google.com/complete/search?client=firefox&ds=yt&q=" + urllib.parse.quote(q)
    with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=6) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    return [str(x) for x in (data[1] if len(data) > 1 else [])][:8]


def library_roots():
    """المجلدات التي يحفظ فيها المساعد (نفس منطق publish_to_gallery)."""
    roots = []
    base = detect_gallery_base()
    if CFG["save"] and CFG["save"] != "off":
        roots.append(CFG["save"])
    elif base:
        roots += [os.path.join(base, "ALTRA-DAWNLOADER"), os.path.join(base, "Movies", "ALTRA"), os.path.join(base, "Music", "ALTRA")]
    roots.append(os.path.join(os.path.expanduser("~"), "altra-downloads"))
    return [os.path.realpath(r) for r in dict.fromkeys(roots) if os.path.isdir(r)]


def library_list():
    import hashlib
    items, seen = [], set()
    roots = library_roots()
    for root in roots:
        for dp, dns, fns in os.walk(root):
            dns[:] = [d for d in dns if not d.startswith(".")]
            if dp[len(root):].count(os.sep) >= 3:
                dns[:] = []
            for fn in fns:
                ext = os.path.splitext(fn)[1].lower()
                fp = os.path.join(dp, fn)
                if ext not in MEDIA_EXTS or fp in seen:
                    continue
                try:
                    st = os.stat(fp)
                except OSError:
                    continue
                seen.add(fp)
                kind = "audio" if ext in (".mp3", ".m4a", ".aac", ".flac", ".wav", ".ogg", ".opus", ".alac", ".weba", ".mka") else ("zip" if ext == ".zip" else "video")
                items.append({"id": hashlib.sha1(fp.encode("utf-8", "replace")).hexdigest()[:16], "name": fn, "size": st.st_size,
                              "mtime": int(st.st_mtime), "kind": kind, "folder": os.path.basename(root), "path": fp})
    items.sort(key=lambda x: x["mtime"], reverse=True)
    items = items[:800]
    with LIB_LOCK:
        LIB.clear()
        for it in items:
            LIB[it["id"]] = it["path"]
    for it in items:
        it.pop("path", None)
    return {"items": items, "roots": [os.path.basename(r) for r in roots],
            "total": sum(i["size"] for i in items)}


def library_path(fid):
    """يحوّل المعرّف إلى مسار، مع التأكد أنه داخل مجلدات الحفظ فقط."""
    with LIB_LOCK:
        p = LIB.get(fid)
    if not p:
        return None
    rp = os.path.realpath(p)
    if not any(rp.startswith(r + os.sep) for r in library_roots()) or not os.path.isfile(rp):
        return None
    return rp


def collect_files(info, jobdir):
    paths = []

    def add(i):
        if not i:
            return
        for rd in (i.get("requested_downloads") or []):
            fp = rd.get("filepath") or rd.get("_filename")
            if fp:
                paths.append(fp)
        for e in (i.get("entries") or []):
            add(e)

    add(info)
    paths = [p for p in dict.fromkeys(paths) if os.path.isfile(p)]
    if not paths:
        for f in sorted(os.listdir(jobdir)):
            fp = os.path.join(jobdir, f)
            if os.path.isfile(fp) and not f.endswith((".part", ".ytdl", ".temp", ".json")):
                paths.append(fp)
    return paths


VIDEO_EXTS = (".mp4", ".m4v", ".mov", ".webm", ".mkv")


def media_ok(path, why=None):
    """يتأكد أن ملف الفيديو سليم وقابل للتشغيل (ffprobe، أو فحص ftyp/moov عند غيابه). why: قائمة تُملأ بالتفاصيل."""
    why = why if why is not None else []
    try:
        size = os.path.getsize(path)
        if size < 2048:
            why.append("حجم الملف صغير جداً (%d بايت)" % size)
            return False
        if not path.lower().endswith(VIDEO_EXTS):
            return True
        if shutil.which("ffprobe"):
            r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                                "format=duration,format_name:stream=codec_type,codec_name",
                                "-of", "json", path], capture_output=True, text=True, timeout=45)
            if r.returncode != 0:
                why.append("ffprobe فشل: " + (r.stderr or "").strip()[:300])
                return False
            j = json.loads(r.stdout or "{}")
            streams = [(x.get("codec_type"), x.get("codec_name")) for x in j.get("streams", [])]
            why.append("حجم %.1f KB · streams=%s · duration=%s" % (size / 1024, streams, (j.get("format") or {}).get("duration")))
            if "video" not in [t for t, _ in streams]:
                why.append("لا يوجد مسار فيديو")
                return False
            try:
                dur = float((j.get("format") or {}).get("duration"))
            except (TypeError, ValueError):
                return True
            if dur <= 0:
                why.append("المدة صفر")
            return dur > 0
        if path.lower().endswith((".mp4", ".m4v", ".mov")):
            with open(path, "rb") as f:
                head = f.read(1 << 20)
                f.seek(max(0, size - (1 << 20)))
                tail = f.read()
            ok = head[4:8] == b"ftyp" and (b"moov" in head or b"moov" in tail)
            why.append("فحص ftyp/moov (ffprobe غير متوفر): " + ("سليم" if ok else "تالف"))
            return ok
        return True
    except Exception as ex:  # noqa: BLE001
        slog("media_ok error: " + repr(ex), "warn")
        return True  # لا نُفشل التحميل بسبب خلل في الفحص نفسه


def run_job(job):
    with SLOTS:
        if job.cancel.is_set():
            if job.pausing:
                job.state, job.phase = "paused", "paused"
                return
            job.state, job.phase = "cancelled", "cancelled"
            job.error = "أُلغي"
            job.finished = time.time()
            return
        job.state, job.phase = "running", "analyzing"
        try:
            if yt_dlp is None:
                raise RuntimeError("yt-dlp غير مثبّت. نفّذ: pip install -U \"yt-dlp[default]\"")
            os.makedirs(job.dir, exist_ok=True)
            holder = {}

            def hook(d):
                if job.cancel.is_set():
                    raise Cancelled()
                st = holder.setdefault("st", {"done": 0})
                s = d.get("status")
                stages = holder.get("stages", 1)
                if s == "downloading":
                    total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                    got = d.get("downloaded_bytes") or 0
                    frac = min(got / total, 1) if total else 0
                    job.progress = max(job.progress, (st["done"] + frac) / stages * 92)
                    job.speed = d.get("speed") or 0
                    job.eta = d.get("eta")
                    job.bytes = job.base_bytes + got
                    job.phase = "downloading"
                elif s == "finished":
                    st["done"] += 1
                    job.base_bytes += d.get("total_bytes") or d.get("downloaded_bytes") or 0
                    job.progress = max(job.progress, min(st["done"] / stages * 92, 92))
                    job.phase = "processing"

            opts, holder["stages"] = build_opts(job, hook)
            slog("بدء: %s · site=%s · quality=%s format=%s mode=%s · ffmpeg=%s · yt-dlp=%s" % (
                job.url, job.site, job.params.get("quality"), job.params.get("format"), job.params.get("mode"),
                CFG["has_ffmpeg"], getattr(getattr(yt_dlp, "version", None), "__version__", None)), "info", job)
            slog("format selector: %s" % opts.get("format"), "info", job)
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(normalize_url(job.url), download=True)
            except Exception as fe:  # noqa: BLE001
                # الصيغة المطلوبة غير متوفرة (شائع في فيسبوك): أعد المحاولة بأوسع اختيار ممكن
                if job.cancel.is_set():
                    raise
                fl = str(fe).lower()
                if "requested format" not in fl:
                    # فشل بسبب إضافة اختيارية (ترجمة/غلاف/وسوم): أعد المحاولة بدونها بدل إفشال المهمة
                    if (job.params.get("subs") or job.params.get("tags")) and re.search(r"subtitle|thumbnail|embed|atomicparsley|mutagen|metadata", fl):
                        slog("فشلت الإضافة الاختيارية (ترجمة/غلاف/وسوم)، إعادة المحاولة بدونها: " + clean_error(fe), "warn", job)
                        strip_extras(opts)
                        with yt_dlp.YoutubeDL(opts) as ydl:
                            info = ydl.extract_info(normalize_url(job.url), download=True)
                    else:
                        raise
                else:
                    slog("الصيغة المطلوبة غير متوفرة، إعادة المحاولة بصيغة أوسع: " + clean_error(fe), "warn", job)
                    opts["format"] = "bv*+ba/b" if CFG["has_ffmpeg"] and not opts.get("postprocessors") else "b/best"
                    opts.pop("merge_output_format", None) if opts["format"] == "b/best" else None
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        info = ydl.extract_info(normalize_url(job.url), download=True)
            if job.cancel.is_set():
                raise Cancelled()
            if not info:
                raise RuntimeError("لم يُعثر على وسائط في هذا الرابط.")
            job.title = (info.get("title") or "")[:200]
            job.thumbnail = info.get("thumbnail") or ""
            job.duration = info.get("duration")
            job.uploader = (info.get("uploader") or info.get("channel") or "")[:80]
            files = collect_files(info, job.dir)
            if not files:
                raise RuntimeError("اكتمل الاستخراج دون إنتاج ملف.")
            if len(files) > 1:
                base = re.sub(r'[\\/:*?"<>|]', "_", job.title or "altra")[:100] or "altra"
                zpath = os.path.join(job.dir, base + ".zip")
                with zipfile.ZipFile(zpath, "w", zipfile.ZIP_STORED) as z:
                    for f in files:
                        z.write(f, os.path.basename(f))
                final = zpath
            else:
                final = files[0]
                why = []
                good = media_ok(final, why)
                slog("فحص الملف %s: %s · %s" % (os.path.basename(final), "سليم" if good else "تالف", " | ".join(why)),
                     "info" if good else "error", job)
                if not good:
                    # الملف تالف/غير قابل للتشغيل (شائع مع إنستغرام عند دمج مسارات DASH): أعد التحميل كملف واحد جاهز
                    job.phase = "processing"
                    try:
                        os.remove(final)
                    except OSError:
                        pass
                    alt = dict(opts)
                    for k in ("postprocessors", "merge_output_format", "postprocessor_args"):
                        alt.pop(k, None)
                    slog("إعادة التحميل كملف واحد (b[ext=mp4]/b/best)…", "warn", job)
                    alt["format"] = "b[ext=mp4]/b/best"
                    alt["outtmpl"] = os.path.join(job.dir, "%(title).120B [%(id)s] (2).%(ext)s")
                    with yt_dlp.YoutubeDL(alt) as ydl:
                        info = ydl.extract_info(normalize_url(job.url), download=True)
                    files = collect_files(info, job.dir)
                    final = files[0] if len(files) == 1 else ""
                    why2 = []
                    good2 = bool(final) and media_ok(final, why2)
                    slog("فحص المحاولة الثانية: %s · %s" % ("سليم" if good2 else "تالف", " | ".join(why2)), "info" if good2 else "error", job)
                    if not good2:
                        raise RuntimeError("الملف الناتج تالف أو غير مكتمل (حاول مرة أخرى، أو حدّث yt-dlp: pip install -U yt-dlp).")
            job.filepath = final
            job.filename = os.path.basename(final)
            job.size = os.path.getsize(final)
            job.bytes = job.size
            publish_to_gallery(job)
            job.progress = 100.0
            job.state, job.phase = "done", "done"
            slog("اكتملت: %s · %.1f KB · محفوظ: %s%s" % (job.filename, job.size / 1024, job.saved or "—",
                 (" · خطأ الحفظ: " + job.save_error) if job.save_error else ""), "info" if not job.save_error else "warn", job)
        except Cancelled:
            if job.pausing:
                job.state, job.phase = "paused", "paused"
                slog("أُوقفت مؤقتاً (الملف الجزئي محفوظ للاستئناف)", "info", job)
            else:
                job.state, job.phase = "cancelled", "cancelled"
                job.error = "أُلغي"
        except Exception as e:  # noqa: BLE001
            if job.cancel.is_set():
                if job.pausing:
                    job.state, job.phase = "paused", "paused"
                else:
                    job.state, job.phase = "cancelled", "cancelled"
                    job.error = "أُلغي"
            else:
                slog("فشل: " + (clean_error(e) or repr(e)) + "\n" + traceback.format_exc(), "error", job)
                job.error = clean_error(e) or "فشل غير معروف"
                job.login = login_needed(job.error, job.url)
                job.hint = explain(job.error) if not job.login else "هذا المحتوى يتطلب تسجيل الدخول. اضغط الشارة الزرقاء في التطبيق لاستيراد جلسة الدخول."
                if not job.hint:
                    job.hint = explain(job.error)
                job.state, job.phase = "error", "error"
        finally:
            if job.state != "paused":
                job.finished = time.time()


def cookies_path():
    return CFG["cookies"] or os.path.join(HERE, "cookies.txt")


def parse_cookies(text):
    """يقبل Netscape (cookies.txt) أو JSON من إضافة Cookie-Editor ويرجع قائمة صفوف Netscape."""
    text = (text or "").strip().lstrip("\ufeff")
    rows = []
    far = int(time.time()) + 30 * 86400
    if text[:1] in ("[", "{"):
        data = json.loads(text)
        if isinstance(data, dict):
            data = data.get("cookies") or []
        for c in data:
            dom, name = str(c.get("domain") or ""), c.get("name")
            if not dom or name is None:
                continue
            exp = c.get("expirationDate") or c.get("expires") or 0
            exp = int(exp) if isinstance(exp, (int, float)) and exp > 0 else far
            clean = lambda v: re.sub(r"[\t\r\n]", "", str(v))
            rows.append([("#HttpOnly_" if c.get("httpOnly") else "") + clean(dom),
                         "TRUE" if dom.startswith(".") else "FALSE", clean(c.get("path") or "/"),
                         "TRUE" if c.get("secure") else "FALSE", str(exp), clean(name), clean(c.get("value") or "")])
    else:
        for line in text.splitlines():
            line = line.rstrip("\r\n")
            if not line.strip() or (line.startswith("#") and not line.startswith("#HttpOnly_")):
                continue
            parts = line.split("\t") if line.count("\t") >= 6 else re.split(r"\s+", line.strip(), maxsplit=6)
            if len(parts) < 7:
                continue
            rows.append(parts[:7])
    return rows


def save_cookies(rows, replace=False):
    path = cookies_path()
    keyed = {}
    if not replace and os.path.isfile(path):
        for r in parse_cookies(open(path, encoding="utf-8", errors="ignore").read()):
            keyed[(r[0].replace("#HttpOnly_", ""), r[2], r[5])] = r
    for r in rows:
        keyed[(r[0].replace("#HttpOnly_", ""), r[2], r[5])] = r
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("# Netscape HTTP Cookie File\n")
        for r in keyed.values():
            f.write("\t".join(r) + "\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return sorted({k[0].lstrip(".") for k in keyed})


def cookie_domains():
    path = cookies_path()
    if not os.path.isfile(path):
        return []
    try:
        rows = parse_cookies(open(path, encoding="utf-8", errors="ignore").read())
    except Exception:
        return []
    return sorted({r[0].replace("#HttpOnly_", "").lstrip(".") for r in rows})


def detect_gallery_base():
    """مجلد التخزين المشترك (أندرويد/Termux) ليظهر الملف في المعرض."""
    if CFG["save"] == "off":
        return None
    if CFG["save"]:
        return CFG["save"]
    home = os.path.expanduser("~")
    for c in (os.path.join(home, "storage", "shared"), "/storage/emulated/0", "/sdcard"):
        if os.path.isdir(c) and os.access(c, os.W_OK):
            return c
    return None


def media_scan(path):
    for cmd in (["termux-media-scan", path],
                ["am", "broadcast", "-a", "android.intent.action.MEDIA_SCANNER_SCAN_FILE", "-d", "file://" + path]):
        if shutil.which(cmd[0]):
            try:
                subprocess.run(cmd, timeout=15, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except Exception:  # noqa: BLE001
                pass
    return False


def publish_to_gallery(job):
    """ينسخ الملف النهائي إلى مجلد ALTRA-DAWNLOADER (Video/Audio) داخل التخزين الداخلي.
    افتراضياً لا يظهر في المعرض/الاستوديو (ملف .nomedia وبلا مسح إعلامي). للظهور فيه شغّل المساعد مع --gallery."""
    base = detect_gallery_base()
    ext = os.path.splitext(job.filepath)[1].lower().lstrip(".")
    is_audio = ext in AUDIO_FORMATS or ext in ("weba", "mka", "aiff")
    is_video = ext in ("mp4", "webm", "mkv", "mov", "m4v", "3gp", "avi", "flv", "gif")
    root = None
    if base and CFG["save"]:
        folder = base
    elif base and CFG["gallery"]:
        folder = os.path.join(base, "Music" if is_audio else ("Movies" if is_video else "Download"), "ALTRA")
    elif base:
        root = os.path.join(base, "ALTRA-DAWNLOADER")
        folder = os.path.join(root, "Audio" if is_audio else ("Video" if is_video else "Other"))
    else:
        folder = os.path.join(os.path.expanduser("~"), "altra-downloads")
    try:
        os.makedirs(folder, exist_ok=True)
        if root:  # يخفي المجلد كله عن المعرض والمشغّلات
            open(os.path.join(root, ".nomedia"), "a").close()
        dest = os.path.join(folder, job.filename)
        n = 1
        stem, e = os.path.splitext(dest)
        while os.path.exists(dest):
            dest = f"{stem} ({n}){e}"
            n += 1
        shutil.copy2(job.filepath, dest)
        job.saved, job.gallery = dest, bool(base and CFG["gallery"])
        slog("نُسخ إلى: %s (%d بايت)" % (dest, os.path.getsize(dest)), "info", job)
        if job.gallery:
            media_scan(dest)
    except Exception as ex:  # noqa: BLE001
        job.save_error = clean_error(ex)
        slog("فشل حفظ الملف: " + repr(ex), "error", job)


def diagnostics():
    base = detect_gallery_base()
    def run(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout.splitlines()[0][:120]
        except Exception as ex:  # noqa: BLE001
            return "خطأ: " + repr(ex)[:100]
    return {
        "helper": VERSION, "python": sys.version.split()[0], "platform": platform.platform()[:100],
        "yt_dlp": getattr(getattr(yt_dlp, "version", None), "__version__", None) if yt_dlp else None,
        "ffmpeg": run(["ffmpeg", "-version"]) if shutil.which("ffmpeg") else None,
        "ffprobe": bool(shutil.which("ffprobe")),
        "js_runtime": [r for r in ("deno", "node", "bun") if shutil.which(r)],
        "gallery_dir": base, "gallery_writable": bool(base and os.access(base, os.W_OK)),
        "cache_dir": CFG["cache"], "cookies": cookie_domains(),
        "origins": sorted(CFG["origins"]), "allow_all": CFG["allow_all"],
        "jobs": len(JOBS), "uptime_s": int(time.time() - START_TIME),
    }


def ytdlp_old():
    try:
        import datetime
        y, m, d = [int(x) for x in yt_dlp.version.__version__.split(".")[:3]]
        return (datetime.date.today() - datetime.date(y, m, d)).days > 75
    except Exception:  # noqa: BLE001
        return False


FB_JUNK = ("fbclid", "mibextid", "rdid", "__cft__[0]", "__tn__", "sfnsn", "refsrc")


def normalize_url(url):
    try:
        u = urlparse(url)
        h = (u.hostname or "").lower()
        if h == "facebook.com" or h.endswith(".facebook.com"):
            from urllib.parse import parse_qsl, urlencode, urlunparse
            q = [(k, v) for k, v in parse_qsl(u.query) if k not in FB_JUNK]
            h = re.sub(r"^(m|web|mbasic|touch|l|lm)\.", "www.", h)
            return urlunparse((u.scheme, h, u.path, u.params, urlencode(q), ""))
    except Exception:  # noqa: BLE001
        pass
    return url


def stale_helpers():
    """عمليات altra-server.py الأخرى (قديمة/معلّقة) تشغل المنفذ؛ نقرأها من /proc دون أي حزمة إضافية."""
    me, out = os.getpid(), []
    try:
        pids = [p for p in os.listdir("/proc") if p.isdigit()]
    except OSError:
        return out
    for p in pids:
        if int(p) == me:
            continue
        try:
            with open(f"/proc/{p}/cmdline", "rb") as f:
                cmd = f.read().split(b"\0")
        except OSError:
            continue
        if any(c.endswith(b"altra-server.py") for c in cmd) and b"python" in (cmd[0] if cmd else b""):
            out.append(int(p))
    return out


def replace_old_helper():
    """يوقف نسخة المساعد القديمة أو المعلّقة (SIGKILL يعمل حتى لو أوقفها أندرويد)."""
    pids = stale_helpers()
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    if pids:
        time.sleep(1.2)
    return pids


def cleaner():
    while True:
        time.sleep(300)
        limit = time.time() - CFG["keep"] * 60
        with JOBS_LOCK:
            stale_pause = time.time() - 6 * 3600
            old = [j for j in JOBS.values() if (j.finished and j.finished < limit) or (j.state == "paused" and j.created < stale_pause)]
            for j in old:
                JOBS.pop(j.id, None)
        for j in old:
            shutil.rmtree(j.dir, ignore_errors=True)


# ── HTTP ───────────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "AltraHelper/" + VERSION

    def log_message(self, fmt, *args):  # صامت
        pass

    # --- مساعدات
    def origin_ok(self):
        origin = self.headers.get("Origin")
        if not origin or CFG["allow_all"]:
            return True
        u = urlparse(origin)
        if u.hostname in ("localhost", "127.0.0.1", "::1"):
            return True
        if u.netloc == self.headers.get("Host"):
            return True
        return origin in CFG["origins"]

    def host_ok(self):
        if not CFG["loopback"]:
            return True
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        return host in ("localhost", "127.0.0.1", "::1", "")

    def cors(self, force=False):
        origin = self.headers.get("Origin")
        if origin and (force or self.origin_ok()):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            req_h = self.headers.get("Access-Control-Request-Headers")
            self.send_header("Access-Control-Allow-Headers", req_h if req_h else "Content-Type")
            self.send_header("Access-Control-Expose-Headers", "Content-Disposition, Content-Length")

    def send_json(self, obj, status=200, force_cors=False):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if self.close_connection:
            self.send_header("Connection", "close")
        self.cors(force_cors)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def guard(self):
        if not self.host_ok():
            self.close_connection = True
            self.send_json({"error": "host not allowed"}, 403)
            return False
        if not self.origin_ok():
            self.close_connection = True
            slog("طلب مرفوض من الموقع: %s" % self.headers.get("Origin"), "warn")
            print(f" ⛔ طلب مرفوض من الموقع: {self.headers.get('Origin')}  ← لو هذا موقعك شغّل المساعد مع:  --origin {self.headers.get('Origin')}")
            o = self.headers.get("Origin")
            self.send_json({"error": "origin not allowed", "origin": o, "fix": "python altra-server.py --origin " + str(o)}, 403, True)
            return False
        return True

    # --- طرق HTTP
    def do_OPTIONS(self):
        if not self.host_ok():
            return self.send_json({"error": "host not allowed"}, 403)
        # الفحص المبدئي يُجاب دائماً ليقرأ التطبيق سبب الرفض؛ أما الطلب الفعلي فيمرّ عبر guard()
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.send_header("Access-Control-Max-Age", "600")
        self.cors(True)
        self.end_headers()

    def do_GET(self):
        if not self.guard():
            return
        path = urlparse(self.path).path
        if path == "/health":
            return self.send_json({
                "ok": True, "altra": True, "version": VERSION,
                "ytdlp": getattr(getattr(yt_dlp, "version", None), "__version__", None) if yt_dlp else None,
                "ffmpeg": CFG["has_ffmpeg"], "ytdlp_old": ytdlp_old(),
                "cookies": bool(cookie_domains()),
                "cookie_domains": cookie_domains(),
            })
        if path == "/api/log":
            q = parse_qs(urlparse(self.path).query)
            try:
                since = int((q.get("since") or ["0"])[0])
            except ValueError:
                since = 0
            with LOG_LOCK:
                rows = [r for r in LOG if r["n"] > since]
                last = LOG_N[0]
            return self.send_json({"logs": rows, "last": last})
        if path == "/api/diag":
            return self.send_json(diagnostics())
        if path == "/api/suggest":
            q = (parse_qs(urlparse(self.path).query).get("q") or [""])[0].strip()[:100]
            if len(q) < 2:
                return self.send_json({"items": []})
            try:
                return self.send_json({"items": suggest(q)})
            except Exception as ex:  # noqa: BLE001
                return self.send_json({"items": [], "error": clean_error(ex)})
        if path == "/api/library":
            try:
                return self.send_json(library_list())
            except Exception as ex:  # noqa: BLE001
                slog("library: " + repr(ex), "error")
                return self.send_json({"items": [], "roots": [], "total": 0, "error": clean_error(ex)})
        m = re.match(r"^/lib/([0-9a-f]{16})$", path)
        if m:
            fp = library_path(m.group(1))
            if not fp:
                return self.send_json({"error": "file not found"}, 404)
            return self.send_file(fp, os.path.basename(fp))
        if path in ("/dashboard", "/admin", "/control"):
            return self.serve_dashboard()
        if path == "/api/jobs":
            with JOBS_LOCK:
                jobs = [j.public() for j in sorted(JOBS.values(), key=lambda x: x.created, reverse=True)]
            return self.send_json({"jobs": jobs, "count": len(jobs)})
        if path == "/api/info":
            cache_size = 0
            cache_files = 0
            try:
                for root, dirs, files in os.walk(CFG["cache"]):
                    for f in files:
                        fp = os.path.join(root, f)
                        try:
                            cache_size += os.path.getsize(fp)
                            cache_files += 1
                        except OSError:
                            pass
            except OSError:
                pass
            with JOBS_LOCK:
                states = {}
                for j in JOBS.values():
                    states[j.state] = states.get(j.state, 0) + 1
            return self.send_json({
                "ok": True, "version": VERSION,
                "ytdlp": getattr(getattr(yt_dlp, "version", None), "__version__", None) if yt_dlp else None,
                "ffmpeg": CFG["has_ffmpeg"], "ytdlp_old": ytdlp_old(),
                "uptime": int(time.time() - START_TIME),
                "jobs_total": sum(states.values()),
                "jobs_by_state": states,
                "cache_size": cache_size,
                "cache_files": cache_files,
                "cache_path": CFG["cache"],
                "gallery": detect_gallery_base(),
                "cookies": bool(cookie_domains()),
                "cookie_domains": cookie_domains(),
                "slots": SLOTS._value if hasattr(SLOTS, "_value") else 6,
            })
        m = re.match(r"^/api/status/([0-9a-f]{16})$", path)
        if m:
            j = JOBS.get(m.group(1))
            return self.send_json(j.public() if j else {"error": "not found"}, 200 if j else 404)
        m = re.match(r"^/file/([0-9a-f]{16})$", path)
        if m:
            j = JOBS.get(m.group(1))
            if not j or j.state != "done" or not os.path.isfile(j.filepath):
                return self.send_json({"error": "file not ready"}, 404)
            return self.send_file(j.filepath, j.filename)
        return self.serve_static(path)

    def do_HEAD(self):
        self.do_GET()

    def do_POST(self):
        if not self.guard():
            return
        path = urlparse(self.path).path
        try:
            n = int(self.headers.get("Content-Length") or 0)
            limit = 2 * 1024 * 1024 if path == "/api/cookies" else 65536
            if n > limit:
                self.close_connection = True
                return self.send_json({"error": "too large"}, 413)
            raw = self.rfile.read(n) if n else b"{}"
            data = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            return self.send_json({"error": "bad json"}, 400)

        if path == "/api/resolve":
            url = str(data.get("url") or "").strip()
            is_search = bool(re.match(r"^(ytsearch|ytsearchdate|youtube:search)\d*:", url, re.I))
            if (not re.match(r"^https?://", url, re.I) and not is_search) or len(url) > 2048:
                return self.send_json({"error": "رابط غير صالح"}, 400)
            q = str(data.get("quality") or "max")
            fmt = str(data.get("format") or "mp4").lower()
            mode = str(data.get("mode") or "auto")
            if not (q == "max" or q.isdigit()):
                q = "max"
            if fmt not in AUDIO_FORMATS | VIDEO_FORMATS:
                fmt = "mp4"
            if mode not in ("auto", "audio", "mute"):
                mode = "auto"
            limit = str(data.get("limit") or "")
            if limit not in RATE_LIMITS:
                limit = ""
            job = Job(url, {"quality": q, "format": fmt, "mode": mode, "limit": limit,
                            "subs": bool(data.get("subs")), "tags": bool(data.get("tags"))})
            with JOBS_LOCK:
                JOBS[job.id] = job
            threading.Thread(target=run_job, args=(job,), daemon=True).start()
            return self.send_json({"id": job.id})

        if path == "/api/cookies":
            try:
                rows = parse_cookies(str(data.get("text") or ""))
            except Exception:
                return self.send_json({"error": "تعذّر قراءة الملف. استخدم cookies.txt أو JSON من Cookie-Editor."}, 400)
            if not rows:
                return self.send_json({"error": "لم أجد أي كوكيز صالحة في النص."}, 400)
            doms = save_cookies(rows, replace=bool(data.get("replace")))
            return self.send_json({"ok": True, "count": len(rows), "domains": doms})
        if path == "/api/cookies/clear":
            try:
                os.remove(cookies_path())
            except OSError:
                pass
            return self.send_json({"ok": True})

        m = re.match(r"^/api/cancel/([0-9a-f]{16})$", path)
        if m:
            j = JOBS.get(m.group(1))
            if j:
                j.pausing = False
                j.cancel.set()
                if j.state == "paused":  # إلغاء مهمة موقوفة مؤقتاً
                    j.state, j.phase, j.error, j.finished = "cancelled", "cancelled", "أُلغي", time.time()
            return self.send_json({"ok": bool(j)})

        m = re.match(r"^/api/pause/([0-9a-f]{16})$", path)
        if m:
            j = JOBS.get(m.group(1))
            if not j or j.state not in ("queued", "running"):
                return self.send_json({"ok": False, "error": "لا يمكن إيقاف هذه المهمة الآن"}, 409)
            j.pausing = True
            j.cancel.set()
            return self.send_json({"ok": True})

        m = re.match(r"^/api/resume/([0-9a-f]{16})$", path)
        if m:
            j = JOBS.get(m.group(1))
            if not j or j.state != "paused":
                return self.send_json({"ok": False, "error": "المهمة ليست موقوفة"}, 409)
            j.pausing = False
            j.resumed = True
            j.cancel.clear()
            j.state, j.phase, j.finished = "queued", "queued", None
            threading.Thread(target=run_job, args=(j,), daemon=True).start()
            return self.send_json({"ok": True})

        if path == "/api/probe":
            url = str(data.get("url") or "").strip()
            query = str(data.get("query") or "").strip()[:150]
            if not query and (not re.match(r"^https?://", url, re.I) or len(url) > 2048):
                return self.send_json({"error": "رابط غير صالح"}, 400)
            try:
                n = int(data.get("n") or 12)
            except (TypeError, ValueError):
                n = 12
            try:
                kind = "playlist" if str(data.get("type") or "") == "playlist" else "video"
                source = "sc" if str(data.get("source") or "") == "sc" else "yt"
                return self.send_json(probe(url, query or None, n, kind, source))
            except Exception as ex:  # noqa: BLE001
                msg = clean_error(ex) or "تعذّرت المعاينة"
                slog("probe فشل: " + msg, "warn")
                return self.send_json({"error": msg, "hint": explain(msg), "login": login_needed(msg, url), "site": site_of(url)}, 502)

        if path == "/api/library/delete":
            fp = library_path(str(data.get("id") or ""))
            if not fp:
                return self.send_json({"error": "الملف غير موجود"}, 404)
            try:
                os.remove(fp)
                slog("حُذف من ملفاتي: " + fp, "info")
            except OSError as ex:
                return self.send_json({"error": clean_error(ex)}, 500)
            return self.send_json({"ok": True})

        if path == "/api/library/rename":
            fp = library_path(str(data.get("id") or ""))
            new = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", str(data.get("name") or "")).strip().strip(".")[:180]
            if not fp or not new:
                return self.send_json({"error": "اسم أو ملف غير صالح"}, 400)
            ext = os.path.splitext(fp)[1]
            if not os.path.splitext(new)[1].lower() == ext.lower():
                new += ext  # يحافظ على الامتداد الأصلي
            dest = os.path.join(os.path.dirname(fp), new)
            if os.path.exists(dest):
                return self.send_json({"error": "يوجد ملف بهذا الاسم"}, 409)
            try:
                os.rename(fp, dest)
            except OSError as ex:
                return self.send_json({"error": clean_error(ex)}, 500)
            return self.send_json({"ok": True, "name": new})

        if path == "/api/jobs/clear":
            # clear finished / cancelled / error jobs
            removed = []
            with JOBS_LOCK:
                to_del = [jid for jid, j in JOBS.items() if j.state in ("done", "cancelled", "error")]
                for jid in to_del:
                    j = JOBS.pop(jid, None)
                    if j:
                        removed.append(jid)
            for jid in removed:
                jdir = os.path.join(CFG["cache"], jid)
                shutil.rmtree(jdir, ignore_errors=True)
            return self.send_json({"ok": True, "removed": len(removed)})

        if path == "/api/cache/clear":
            # clear entire cache and all jobs
            with JOBS_LOCK:
                JOBS.clear()
            shutil.rmtree(CFG["cache"], ignore_errors=True)
            os.makedirs(CFG["cache"], exist_ok=True)
            return self.send_json({"ok": True})

        if path == "/api/cancel-all":
            count = 0
            with JOBS_LOCK:
                for j in JOBS.values():
                    if j.state in ("queued", "running", "paused"):
                        j.cancel.set()
                        if j.state == "paused":
                            j.state, j.phase, j.error, j.finished = "cancelled", "cancelled", "أُلغي", time.time()
                        count += 1
            return self.send_json({"ok": True, "cancelled": count})

        return self.send_json({"error": "not found"}, 404)

    # --- ملفات
    def send_file(self, path, fname):
        size = os.path.getsize(path)
        start, end, status = 0, size - 1, 200
        rng = self.headers.get("Range")
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)$", rng.strip())
            if m:
                a, b = m.groups()
                if a == "" and b != "":
                    start = max(0, size - int(b))
                elif a != "":
                    start = int(a)
                    end = int(b) if b else size - 1
                end = min(end, size - 1)
                if start > end or start >= size:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.cors()
                    self.end_headers()
                    return
                status = 206
        ctype = mimetypes.guess_type(fname)[0] or "application/octet-stream"
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        ascii_name = re.sub(r"[^A-Za-z0-9._-]", "_", fname) or "download"
        self.send_header("Content-Disposition",
                         f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(fname)}")
        self.send_header("Cache-Control", "no-store")
        self.cors()
        self.end_headers()
        if self.command == "HEAD":
            return
        try:
            with open(path, "rb") as f:
                f.seek(start)
                left = length
                while left > 0:
                    chunk = f.read(min(262144, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def serve_dashboard(self):
        html = DASHBOARD_HTML
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def serve_static(self, path):
        rel = unquote(path.lstrip("/")) or "index.html"
        full = os.path.realpath(os.path.join(HERE, rel))
        ext = os.path.splitext(full)[1].lower()
        if not full.startswith(HERE + os.sep) or not os.path.isfile(full) or ext not in STATIC_OK:
            return self.send_json({"error": "not found"}, 404)
        with open(full, "rb") as f:
            body = f.read()
        ctype = "application/manifest+json" if ext == ".webmanifest" else (mimetypes.guess_type(full)[0] or "application/octet-stream")
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)


def main():
    ap = argparse.ArgumentParser(description="ALTRA helper server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--cookies", help="ملف cookies.txt (صيغة Netscape)")
    ap.add_argument("--browser", help="قراءة الكوكيز من متصفح (chrome, firefox, edge...) على الكمبيوتر")
    ap.add_argument("--origin", action="append", default=[], help="سماح لموقع إضافي، أو * للجميع")
    ap.add_argument("--cache", help="مجلد الملفات المؤقتة")
    ap.add_argument("--keep", type=int, default=60, help="مدة حفظ الملفات المؤقتة بالدقائق")
    ap.add_argument("--save-dir", help="مجلد حفظ نسخة نهائية (افتراضياً: معرض الجوال في Termux)، أو off للتعطيل")
    ap.add_argument("--gallery", action="store_true", help="إظهار الملفات في معرض/استوديو الجوال (افتراضياً مخفية في مجلد ALTRA-DAWNLOADER)")
    ap.add_argument("--update", action="store_true", help="حدّث yt-dlp قبل التشغيل")
    ap.add_argument("--jobs", type=int, default=10, help="عدد التحميلات المتزامنة في المساعد")
    a = ap.parse_args()
    if a.update:
        print("▶ تحديث yt-dlp …")
        for pkg in ("yt-dlp[default]", "yt-dlp"):
            if subprocess.run([sys.executable, "-m", "pip", "install", "-U", "-q", pkg]).returncode == 0:
                break
        os.execv(sys.executable, [sys.executable] + [x for x in sys.argv if x != "--update"])

    CFG["cookies"] = a.cookies
    CFG["browser"] = a.browser
    CFG["keep"] = a.keep
    CFG["gallery"] = bool(a.gallery)
    CFG["save"] = os.path.abspath(a.save_dir) if a.save_dir and a.save_dir != "off" else ("off" if a.save_dir == "off" else None)
    CFG["loopback"] = a.host in ("127.0.0.1", "localhost", "::1")
    for o in a.origin:
        if o == "*":
            CFG["allow_all"] = True
        else:
            CFG["origins"].add(o.rstrip("/"))
    if a.cache:
        CFG["cache"] = os.path.abspath(a.cache)
    global SLOTS
    SLOTS = threading.BoundedSemaphore(max(1, a.jobs))

    shutil.rmtree(CFG["cache"], ignore_errors=True)
    os.makedirs(CFG["cache"], exist_ok=True)
    threading.Thread(target=cleaner, daemon=True).start()

    srv = None
    for attempt in range(2):
        try:
            srv = ThreadingHTTPServer((a.host, a.port), Handler)
            break
        except OSError as e:
            old = replace_old_helper() if attempt == 0 else []
            if old:
                print(f" ♻ وُجدت نسخة قديمة/معلّقة من المساعد على المنفذ {a.port} (PID {', '.join(map(str, old))}) وأُوقفت، أعيد التشغيل…")
                continue
            print(f"تعذّر فتح المنفذ {a.port}: {e}\nبرنامج آخر يستخدمه. جرّب منفذاً آخر:  python altra-server.py --port {a.port + 1}\n(وضع نفس المنفذ في خانة «عنوان المساعد» بالتطبيق)")
            sys.exit(1)
    srv.daemon_threads = True
    # يمنع أندرويد من تجميد Termux في الخلفية (وهو سبب «غير متصل» رغم أن المنفذ مشغول)
    if shutil.which("termux-wake-lock"):
        try:
            subprocess.Popen(["termux-wake-lock"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            pass

    ver = getattr(getattr(yt_dlp, "version", None), "__version__", None) if yt_dlp else None
    print("═" * 56)
    print(f" ALTRA Helper v{VERSION}")
    print(f" yt-dlp : {ver or 'غير مثبّت  ←  pip install -U \"yt-dlp[default]\"'}")
    g = detect_gallery_base()
    print(f" الحفظ  : {(g + ('/Movies/ALTRA (المعرض)' if CFG['gallery'] else '/ALTRA-DAWNLOADER (مخفي عن المعرض)')) if g and not CFG['save'] else g or '~/altra-downloads  (للحفظ في التخزين الداخلي نفّذ: termux-setup-storage ثم أعد التشغيل)'}")
    if ytdlp_old():
        print(" ⚠ نسخة yt-dlp قديمة: شغّل مع --update أو  pip install -U yt-dlp")
    print(f" ffmpeg : {'متوفر' if CFG['has_ffmpeg'] else 'غير موجود (الدمج والتحويل معطّلان)'}")
    print(f" العنوان: http://{'localhost' if CFG['loopback'] else a.host}:{a.port}")
    print(f" لوحة التحكم: http://{'localhost' if CFG['loopback'] else a.host}:{a.port}/dashboard")
    if os.environ.get("PREFIX", "").startswith("/data/data/com.termux"):
        print(" 🔋 لتجنّب تجميد أندرويد للمساعد: إعدادات الجوال ← البطارية ← Termux ← «غير مقيّد»")
    print(" اترك هذه النافذة مفتوحة أثناء التحميل.  إيقاف: Ctrl+C")
    print("═" * 56)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nتم الإيقاف.")
    finally:
        shutil.rmtree(CFG["cache"], ignore_errors=True)


if __name__ == "__main__":
    main()
