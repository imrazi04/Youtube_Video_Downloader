from flask import Flask, Response, jsonify, request, render_template
from flask_cors import CORS
import json
import os
import queue
import re
import shutil
import tempfile
import threading
import time
import yt_dlp


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

# Spoof a real browser so YouTube doesn't reset the connection (WinError 10054)
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,video/mp4,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Sec-Fetch-Mode": "navigate",
}

# Only /tmp is writable on Vercel; the system temp dir works locally too.
_TMP = tempfile.gettempdir()
os.environ.setdefault("DENO_DIR", os.path.join(_TMP, "deno"))

_RESOLUTIONS = {"360p": 360, "480p": 480, "720p": 720, "1080p": 1080}
_CHUNK_SIZE  = 1024 * 1024

# YouTube randomly serves "limited" sessions (SABR experiment) that expose only
# 360p, or stream URLs that 403 mid-download. A fresh extraction usually gets a
# normal session, so we retry the whole extract + download a few times.
_ATTEMPTS = 3


def _find_deno():
    """Deno (pip package) solves YouTube's JS challenges — without it YouTube says 'video not available'."""
    try:
        import deno
        return deno.find_deno_bin()
    except Exception:
        return shutil.which("deno")


def _find_ffmpeg():
    """FFmpeg (imageio-ffmpeg package) merges separate video + audio streams."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return shutil.which("ffmpeg")


def _cookie_file():
    """
    Optional: YouTube often blocks datacenter IPs (e.g. Vercel) with
    "Sign in to confirm you're not a bot". Put the contents of a Netscape
    cookies.txt in the YTDLP_COOKIES env var to authenticate.
    """
    cookies = os.environ.get("YTDLP_COOKIES")
    if not cookies:
        return None
    path = os.path.join(_TMP, "yt-cookies.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(cookies)
    return path


def _base_opts():
    """yt-dlp options shared by info extraction and downloads."""
    opts = {
        "quiet":              True,
        "no_warnings":        True,
        "nocheckcertificate": True,
        "http_headers":       _BROWSER_HEADERS,
        "socket_timeout":     30,
        "cachedir":           os.path.join(_TMP, "yt-dlp-cache"),
    }
    deno_bin = _find_deno()
    if deno_bin:
        opts["js_runtimes"] = {"deno": {"path": deno_bin}}
    ffmpeg_bin = _find_ffmpeg()
    if ffmpeg_bin:
        opts["ffmpeg_location"] = ffmpeg_bin
    cookie_file = _cookie_file()
    if cookie_file:
        opts["cookiefile"] = cookie_file
    if os.environ.get("YTDLP_PROXY"):
        opts["proxy"] = os.environ["YTDLP_PROXY"]
    return opts


def _clean_error(exc):
    """Turn a yt-dlp exception into a short, readable message."""
    msg = _ANSI_RE.sub("", str(exc)).replace("ERROR: ", "").strip()
    if "not a bot" in msg or "Sign in to confirm" in msg:
        msg += (
            " — YouTube is blocking this server's IP. Set the YTDLP_COOKIES "
            "(or YTDLP_PROXY) environment variable; see README."
        )
    elif "10054" in msg or "forcibly closed" in msg.lower():
        msg = "Connection reset by YouTube. Please wait a moment and try again."
    return msg


def _resolutions_in(info):
    """Set of supported resolution labels that have a video stream."""
    label_map = {height: label for label, height in _RESOLUTIONS.items()}
    found = set()

    for fmt in info.get("formats") or []:
        # 1. Prefer the raw integer height field — most reliable
        height = fmt.get("height")

        # 2. Fall back to parsing "WIDTHxHEIGHT" resolution string
        if not isinstance(height, int) or height <= 0:
            m = re.search(r"x(\d+)$", str(fmt.get("resolution") or ""))
            if m:
                height = int(m.group(1))

        # 3. Fall back to parsing format_note like "720p" or "1080p60"
        if not isinstance(height, int) or height <= 0:
            m = re.search(r"(\d+)p", str(fmt.get("format_note") or ""))
            if m:
                height = int(m.group(1))

        if height in label_map and fmt.get("vcodec") not in (None, "", "none"):
            found.add(label_map[height])
    return found


def _is_limited_session(info):
    """Limited (SABR) sessions expose a single muxed 360p format and nothing else."""
    video_formats = [f for f in info.get("formats") or [] if f.get("vcodec") not in (None, "", "none")]
    return len(video_formats) <= 1


def _is_session_error(exc):
    """Errors that a fresh YouTube session (new extraction) can fix."""
    msg = str(exc)
    return "403" in msg or "Forbidden" in msg or "Requested format is not available" in msg


def _json_line(obj):
    return (json.dumps(obj) + "\n").encode()


def _download_job(url, target_height, events, cancelled):
    """
    Runs in a worker thread: downloads the video with yt-dlp into a temp dir,
    pushing progress events onto `events`. Ends with a "file" or "error" event.
    """
    work_dir = tempfile.mkdtemp(prefix="ytdl-", dir=_TMP)
    progress = {"done": 0, "total": 0, "last": 0.0}

    def on_progress(d):
        if cancelled.is_set():
            raise yt_dlp.utils.DownloadCancelled("Browser disconnected")
        if d["status"] == "finished":
            # Video and audio are separate files; count finished ones toward the total
            progress["done"] += d.get("total_bytes") or d.get("downloaded_bytes") or 0
            return
        now = time.monotonic()
        if d["status"] != "downloading" or now - progress["last"] < 0.3:
            return
        progress["last"] = now
        got   = progress["done"] + (d.get("downloaded_bytes") or 0)
        total = progress["total"] or d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        events.put({
            "type":    "progress",
            "percent": round(min(got / total * 100, 99.9), 1) if total else 0,
            "speed":   d.get("speed") or 0,
            "eta":     d.get("eta"),
        })

    def on_postprocess(d):
        if d["status"] == "started" and d["postprocessor"] == "Merger":
            events.put({"type": "status", "message": "Merging video and audio…"})

    ydl_opts = {
        **_base_opts(),
        "noplaylist":          True,
        "noprogress":          True,
        "outtmpl":             os.path.join(work_dir, "%(title).150B.%(ext)s"),
        "merge_output_format": "mp4",
        "format": (
            # Prefer H.264 + AAC so the MP4 plays in every player
            f"bestvideo[height<={target_height}][vcodec^=avc1]+bestaudio[ext=m4a]"
            f"/bestvideo[height<={target_height}][ext=mp4]+bestaudio[ext=m4a]"
            f"/bestvideo[height<={target_height}]+bestaudio"
            f"/best[height<={target_height}]/best"
        ),
        "retries":             10,
        "fragment_retries":    10,
        "progress_hooks":      [on_progress],
        "postprocessor_hooks": [on_postprocess],
    }

    for attempt in range(_ATTEMPTS):
        last_try = attempt == _ATTEMPTS - 1
        if attempt:
            events.put({"type": "status", "message": f"YouTube limited this session — retrying ({attempt + 1}/{_ATTEMPTS})…"})
        else:
            events.put({"type": "status", "message": "Connecting to YouTube…"})
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                # A limited session makes the format fallback pick a lower
                # quality than requested; get a fresh session instead.
                if _is_limited_session(info) and (info.get("height") or 0) < target_height and not last_try:
                    continue
                progress.update(done=0, total=sum(
                    f.get("filesize") or f.get("filesize_approx") or 0
                    for f in info.get("requested_formats") or [info]
                ))
                events.put({"type": "status", "message": "Downloading from YouTube…"})
                ydl.process_ie_result(info, download=True)
            files = [f for f in os.listdir(work_dir) if not f.endswith((".part", ".ytdl"))]
            if not files:
                raise RuntimeError("Download finished but no file was produced.")
            path = os.path.join(work_dir, files[0])
            events.put({"type": "file", "name": files[0], "size": os.path.getsize(path),
                        "path": path, "dir": work_dir})
            return
        except Exception as exc:
            for leftover in os.listdir(work_dir):
                os.remove(os.path.join(work_dir, leftover))
            if cancelled.is_set() or last_try or not _is_session_error(exc):
                shutil.rmtree(work_dir, ignore_errors=True)
                events.put({"type": "error", "error": _clean_error(exc)})
                return


def create_app():
    app = Flask(__name__)
    CORS(app)

    app.config["YTDLP_VERSION"] = yt_dlp.version.__version__

    # ── Serve the frontend ────────────────────────────────────────
    @app.route("/", methods=["GET"])
    def index():
        return render_template("index.html")

    # ── Health check ──────────────────────────────────────────────
    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({
            "status":         "ok",
            "yt_dlp_version": app.config["YTDLP_VERSION"],
            "deno":           bool(_find_deno()),
            "ffmpeg":         bool(_find_ffmpeg()),
        })

    # ── Fetch video metadata ──────────────────────────────────────
    @app.route("/get-info", methods=["POST"])
    def get_info():
        payload = request.get_json(silent=True)
        if not payload or not isinstance(payload, dict):
            return jsonify({"error": "Invalid JSON body."}), 400

        url = payload.get("url")
        if not url or not isinstance(url, str):
            return jsonify({"error": "A valid 'url' field is required."}), 400

        ydl_opts = {**_base_opts(), "skip_download": True, "noplaylist": True, "retries": 5}

        best_info, best_found = None, set()
        for attempt in range(_ATTEMPTS):
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
            except Exception as exc:
                if best_info is None and (attempt == _ATTEMPTS - 1 or not _is_session_error(exc)):
                    return jsonify({"error": _clean_error(exc)}), 400
                continue

            found = _resolutions_in(info)
            if best_info is None or len(found) > len(best_found):
                best_info, best_found = info, found
            if not _is_limited_session(info):
                break

        info, found = best_info, best_found
        return jsonify({
            "title":                 info.get("title"),
            "thumbnail":             info.get("thumbnail"),
            "duration":              info.get("duration"),
            "available_resolutions": [r for r in _RESOLUTIONS if r in found],
        })

    # ── Download & stream the file to the browser ─────────────────
    @app.route("/download", methods=["POST"])
    def download():
        payload = request.get_json(silent=True)
        if not payload or not isinstance(payload, dict):
            return jsonify({"error": "Invalid JSON body."}), 400

        url        = payload.get("url")
        resolution = payload.get("resolution")

        if not url or not isinstance(url, str):
            return jsonify({"error": "A valid 'url' field is required."}), 400
        if resolution not in _RESOLUTIONS:
            return jsonify({"error": f"Invalid resolution. Choose from: {list(_RESOLUTIONS)}"}), 400

        events    = queue.Queue()
        cancelled = threading.Event()
        threading.Thread(
            target=_download_job,
            args=(url, _RESOLUTIONS[resolution], events, cancelled),
            daemon=True,
        ).start()

        # One streamed response: JSON progress lines while the server downloads
        # from YouTube, then a {"type": "file"} header line followed by the raw
        # file bytes. Streaming keeps it to a single request, which works on
        # Vercel (no shared state between instances, no 4.5 MB body limit).
        def stream():
            try:
                while True:
                    event = events.get()
                    if event["type"] == "file":
                        yield _json_line({"type": "file", "name": event["name"], "size": event["size"]})
                        try:
                            with open(event["path"], "rb") as f:
                                while chunk := f.read(_CHUNK_SIZE):
                                    yield chunk
                        finally:
                            shutil.rmtree(event["dir"], ignore_errors=True)
                        return
                    yield _json_line(event)
                    if event["type"] == "error":
                        return
            finally:
                cancelled.set()  # browser closed the page → stop the download

        return Response(stream(), mimetype="application/x-ndjson", headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
        })

    return app


# Vercel looks for a top-level `app` in app.py
app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
