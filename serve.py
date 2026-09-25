"""
Production server for running the downloader from your own PC.

    python serve.py

Serves on http://localhost:5000. Use start.ps1 to also open a public
Cloudflare Tunnel link so others can use it.
"""
import os
from waitress import serve
from app import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"YouTube Downloader running on http://localhost:{port}  (Ctrl+C to stop)", flush=True)
    serve(
        app,
        host="127.0.0.1",   # only reachable through the tunnel / this PC
        port=port,
        threads=16,         # each download holds a thread for its whole duration
        channel_timeout=600,
        send_bytes=1,       # flush small progress lines immediately instead of buffering
    )
