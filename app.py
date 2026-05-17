from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
import glob
import re
import os
import threading
import yt_dlp


# Global progress store for the current download session
_download_progress = {
    "percent": "",
    "speed": "",
    "status": "idle",  # idle | starting | downloading | finished | error
    "filename": "",
    "error": None,
}
_download_lock = threading.Lock()


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


def _clean(s):
    """Strip ANSI escape codes and whitespace from a string."""
    return _ANSI_RE.sub("", str(s)).strip() if s else ""


def _fmt_speed(bps):
    """Format bytes/sec to a human-readable string without ANSI codes."""
    if not bps:
        return ""
    for unit in ("B/s", "KiB/s", "MiB/s", "GiB/s"):
        if bps < 1024:
            return f"{bps:.2f} {unit}"
        bps /= 1024
    return f"{bps:.2f} TiB/s"


def progress_hook(d):
    """yt-dlp progress hook — updates global progress state."""
    with _download_lock:
        if d["status"] == "downloading":
            # Compute percent from raw bytes to avoid ANSI-coded _percent_str
            downloaded = d.get("downloaded_bytes") or 0
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            pct = f"{downloaded / total * 100:.1f}%" if total > 0 else "0.0%"

            # Format speed from raw bytes/s to avoid ANSI-coded _speed_str
            speed = _fmt_speed(d.get("speed")) or _clean(d.get("_speed_str", ""))

            _download_progress["status"]  = "downloading"
            _download_progress["percent"] = pct
            _download_progress["speed"]   = speed
            _download_progress["error"]   = None
        elif d["status"] == "finished":
            _download_progress["status"]   = "finished"
            _download_progress["percent"]  = "100%"
            _download_progress["speed"]    = ""
            _download_progress["filename"] = d.get("filename", "")
            _download_progress["error"]    = None


def get_downloads_folder():
    """Return the system Downloads folder (Windows / macOS / Linux)."""
    return os.path.join(os.path.expanduser("~"), "Downloads")


def cleanup_partial_files(folder):
    """Remove leftover yt-dlp partial download files (.part / .ytdl)."""
    for pattern in ("*.part", "*.ytdl"):
        for path in glob.glob(os.path.join(folder, pattern)):
            try:
                os.remove(path)
            except OSError:
                pass


def download_worker(url, resolution):
    """Background worker: runs yt-dlp and updates global progress."""
    res_map = {"360p": 360, "480p": 480, "720p": 720, "1080p": 1080}
    target_height = res_map.get(resolution, 720)

    downloads_folder = get_downloads_folder()
    output_template  = os.path.join(downloads_folder, "%(title)s.%(ext)s")

    format_selector = (
        f"bestvideo[height<={target_height}][vcodec!=none][acodec=none]"
        f"+bestaudio[acodec!=none][vcodec=none]"
        f"/best[height<={target_height}]"
    )

    ydl_opts = {
        "quiet":               True,
        "nocheckcertificate":  True,
        "ignorewarnings":      True,
        "outtmpl":             output_template,
        "progress_hooks":      [progress_hook],
        "merge_output_format": "mp4",
        "format":              format_selector,
        "http_headers":        _BROWSER_HEADERS,
        "socket_timeout":      30,
        "retries":             10,
        "fragment_retries":    10,
    }

    with _download_lock:
        _download_progress["status"] = "starting"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        # Ensure finished state is set even if the hook didn't fire last
        with _download_lock:
            _download_progress["status"]  = "finished"
            _download_progress["percent"] = "100%"
            _download_progress["speed"]   = ""
            _download_progress["error"]   = None
    except yt_dlp.utils.DownloadError as exc:
        msg = str(exc).strip()
        if "10054" in msg or "forcibly closed" in msg.lower():
            msg = (
                "Connection reset by YouTube (WinError 10054). "
                "YouTube throttled or blocked the request after retries. "
                "Please wait a moment and try again."
            )
        with _download_lock:
            _download_progress["status"] = "error"
            _download_progress["error"]  = msg
        cleanup_partial_files(downloads_folder)
    except Exception as exc:
        msg = str(exc)
        if "10054" in msg or "forcibly closed" in msg.lower():
            msg = (
                "Connection lost mid-download (WinError 10054). "
                "YouTube may be throttling your IP. Please retry in a moment."
            )
        else:
            msg = f"Download failed: {exc}"
        with _download_lock:
            _download_progress["status"] = "error"
            _download_progress["error"]  = msg
        cleanup_partial_files(downloads_folder)


def create_app():
    app = Flask(__name__)
    CORS(app)

    yt_dlp_version = getattr(yt_dlp, "__version__", None)
    if yt_dlp_version is None and hasattr(yt_dlp, "version"):
        yt_dlp_version = getattr(yt_dlp.version, "__version__", None)
    app.config["YTDLP_VERSION"] = yt_dlp_version

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

        ydl_opts = {
            "quiet":              True,
            "skip_download":      True,
            "nocheckcertificate": True,
            "ignorewarnings":     True,
            "http_headers":       _BROWSER_HEADERS,
            "socket_timeout":     30,
            "retries":            5,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as exc:
            return jsonify({"error": str(exc).strip()}), 400
        except Exception as exc:
            return jsonify({"error": f"Unable to extract video info: {exc}"}), 400

        title     = info.get("title")
        thumbnail = info.get("thumbnail")
        duration  = info.get("duration")

        formats = info.get("formats") or []
        label_map = {360: "360p", 480: "480p", 720: "720p", 1080: "1080p"}
        desired_order = ["360p", "480p", "720p", "1080p"]
        video_audio_resolutions = []
        video_only_resolutions  = []

        for fmt in formats:
            # 1. Prefer the raw integer height field — most reliable
            height = fmt.get("height")

            # 2. Fall back to parsing "WIDTHxHEIGHT" resolution string
            if not isinstance(height, int) or height <= 0:
                res_str = str(fmt.get("resolution") or "")
                m = re.search(r"x(\d+)$", res_str)
                if m:
                    height = int(m.group(1))

            # 3. Fall back to parsing format_note like "720p" or "1080p60"
            if not isinstance(height, int) or height <= 0:
                note = str(fmt.get("format_note") or "")
                m = re.search(r"(\d+)p", note)
                if m:
                    height = int(m.group(1))

            resolution = label_map.get(height)
            if not resolution:
                continue

            has_video = fmt.get("vcodec") not in (None, "", "none")
            has_audio = fmt.get("acodec") not in (None, "", "none")

            if has_video and has_audio:
                if resolution not in video_audio_resolutions:
                    video_audio_resolutions.append(resolution)
            elif has_video and not has_audio:
                if resolution not in video_only_resolutions:
                    video_only_resolutions.append(resolution)

        available_resolutions = [r for r in desired_order if r in video_audio_resolutions]
        fallback_resolutions  = [
            r for r in desired_order
            if r in video_only_resolutions and r not in video_audio_resolutions
        ]

        return jsonify({
            "title":                 title,
            "thumbnail":             thumbnail,
            "duration":              duration,
            "available_resolutions": available_resolutions,
            "video_only_resolutions": fallback_resolutions,
        })

    # ── Start download ────────────────────────────────────────────
    @app.route("/download", methods=["POST"])
    def start_download():
        global _download_progress

        payload = request.get_json(silent=True)
        if not payload or not isinstance(payload, dict):
            return jsonify({"error": "Invalid JSON body."}), 400

        url        = payload.get("url")
        resolution = payload.get("resolution")

        if not url or not isinstance(url, str):
            return jsonify({"error": "A valid 'url' field is required."}), 400
        if not resolution or not isinstance(resolution, str):
            return jsonify({"error": "A valid 'resolution' field is required (360p, 480p, 720p, 1080p)."}), 400

        valid_resolutions = ["360p", "480p", "720p", "1080p"]
        if resolution not in valid_resolutions:
            return jsonify({"error": f"Invalid resolution. Choose from: {valid_resolutions}"}), 400

        with _download_lock:
            _download_progress = {
                "percent":  "",
                "speed":    "",
                "status":   "starting",
                "filename": "",
                "error":    None,
            }

        thread = threading.Thread(
            target=download_worker,
            args=(url, resolution),
            daemon=True,
        )
        thread.start()

        return jsonify({
            "message":    "Download started",
            "resolution": resolution,
            "status":     "starting",
        }), 202

    # ── Poll progress ─────────────────────────────────────────────
    @app.route("/progress", methods=["GET"])
    def get_progress():
        with _download_lock:
            return jsonify(_download_progress.copy())

    # ── Manual reset (clears error/finished state) ────────────────
    @app.route("/reset", methods=["POST"])
    def reset_progress():
        global _download_progress
        with _download_lock:
            _download_progress = {
                "percent":  "",
                "speed":    "",
                "status":   "idle",
                "filename": "",
                "error":    None,
            }
        return jsonify({"status": "idle", "message": "Progress reset."})

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True)
