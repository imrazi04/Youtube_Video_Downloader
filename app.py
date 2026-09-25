from flask import Flask, Response, jsonify, request, render_template
from flask_cors import CORS
from urllib.parse import quote
import os
import re
import shutil
import tempfile
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


def _content_disposition(filename):
    """Attachment header that survives non-ASCII video titles."""
    ascii_name = filename.encode("ascii", "ignore").decode() or "video.mp4"
    ascii_name = ascii_name.replace('"', "")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


def create_app():
    app = Flask(__name__)
    CORS(app, expose_headers=["Content-Disposition", "Content-Length"])

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

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as exc:
            return jsonify({"error": _clean_error(exc)}), 400

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

        target_height = _RESOLUTIONS[resolution]
        work_dir = tempfile.mkdtemp(prefix="ytdl-", dir=_TMP)

        ydl_opts = {
            **_base_opts(),
            "noplaylist":          True,
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
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            files = [f for f in os.listdir(work_dir) if not f.endswith((".part", ".ytdl"))]
            if not files:
                raise RuntimeError("Download finished but no file was produced.")
        except Exception as exc:
            shutil.rmtree(work_dir, ignore_errors=True)
            return jsonify({"error": _clean_error(exc)}), 400

        filename = files[0]
        path     = os.path.join(work_dir, filename)
        size     = os.path.getsize(path)

        # Stream in chunks (Vercel only allows >4.5 MB responses when streamed),
        # then delete the temp copy once the browser has it.
        def stream():
            try:
                with open(path, "rb") as f:
                    while chunk := f.read(_CHUNK_SIZE):
                        yield chunk
            finally:
                shutil.rmtree(work_dir, ignore_errors=True)

        return Response(stream(), mimetype="application/octet-stream", headers={
            "Content-Disposition": _content_disposition(filename),
            "Content-Length":      str(size),
        })

    return app


# Vercel looks for a top-level `app` in app.py
app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
