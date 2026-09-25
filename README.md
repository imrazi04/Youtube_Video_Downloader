# YouTube Video Downloader

A modern, browser-based YouTube video downloader built with Flask and yt-dlp. Paste a URL, pick a resolution, and the video downloads through your browser. It runs on your own PC and can be shared online through a free Cloudflare Tunnel link.

---

## Features

- Clean single-page UI with live progress bar
- Supports 360p, 480p, 720p, and 1080p
- Automatic video + audio merging (FFmpeg is bundled via `imageio-ffmpeg`, no manual install)
- YouTube JS-challenge solving (Deno is bundled via pip, no manual install)
- Success notification with 5-second auto-reset
- Error display with one-click Retry

---

## Run Locally

Requires Python 3.9+.

```bash
git clone https://github.com/imrazi04/Youtube_Video_Downloader.git
cd Youtube_Video_Downloader

python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # macOS / Linux

pip install -r requirements.txt
python app.py
```

Open http://localhost:5000.

---

## Share It Online (hosted from your PC)

YouTube blocks cloud/data-center IPs (Vercel, VPS, Render, …) with *"Sign in to confirm you're not a bot"*, and cookie workarounds expire quickly. A home internet connection isn't blocked. So the app runs on your PC, and a free **Cloudflare Tunnel** gives it a public HTTPS link. There's no router or port-forwarding setup, no cookies and no environment variables.

**One-time setup**

```powershell
winget install --id Cloudflare.cloudflared
pip install -r requirements.txt
```

**Start it**

Double-click **`start.bat`**. It starts the production server (`serve.py`, using waitress) and the tunnel, then prints a public link like `https://random-words.trycloudflare.com` and copies it to your clipboard. Share that link.

- Keep the window open, and keep the PC awake. Closing the window stops both.
- The link changes each time you restart. For a permanent link on your own domain, create a *named tunnel* with a free Cloudflare account (see [Cloudflare's tunnel guide](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/get-started/)).
- Downloads run through your internet connection, so share the link only with people you trust.

**Run locally only (no public link)**

```powershell
python serve.py      # production server on http://localhost:5000
python app.py        # or: Flask dev server with auto-reload, for development
```

---

## How to Use

1. **Paste** a YouTube video URL into the input field and click **Fetch**.
2. **Select** your preferred resolution.
3. Click **Download**. The server first fetches the video from YouTube, then streams it to your browser with a live progress bar.
4. The file is saved by your browser (usually to your **Downloads** folder).

---

## Project Structure

```
Youtube_Video_Downloader/
├── app.py              # Flask backend (API + serves frontend)
├── serve.py            # Production server (waitress)
├── start.ps1 / start.bat  # Starts server + public Cloudflare Tunnel link
├── requirements.txt    # Python dependencies
└── templates/
    └── index.html      # Single-page frontend
```

---

## API Endpoints

| Method | Endpoint    | Description                                          |
|--------|-------------|------------------------------------------------------|
| GET    | `/`         | Serves the web UI                                    |
| GET    | `/health`   | Status, extractor and version, and `ready` once deno + ffmpeg are found |
| POST   | `/get-info` | Fetch video metadata and resolutions                 |
| POST   | `/download` | Download the video and stream the MP4 in the response |

```json
// /get-info
{ "url": "https://www.youtube.com/watch?v=..." }

// /download
{ "url": "https://www.youtube.com/watch?v=...", "resolution": "720p" }
```

Invalid requests return `{ "error": "..." }` with HTTP 400.

`/download` streams newline-delimited JSON progress events, then the file, all in one response:

```
{"type": "status",   "message": "Downloading from YouTube…"}
{"type": "progress", "percent": 42.5, "speed": 5242880, "eta": 12}
{"type": "file",     "name": "Video title.mp4", "size": 123456789}
<exactly `size` raw bytes of the MP4>
```

If something fails, the stream ends with `{"type": "error", "error": "..."}` instead of a `file` line.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `This video is not available` for a working video | yt-dlp is outdated or has no JS runtime. Run `pip install -U -r requirements.txt`. |
| `Sign in to confirm you're not a bot` | The app is running on a cloud/data-center IP. Run it from your home PC (see above). |
| `The page needs to be reloaded` | YouTube changed something. Run `pip install -U -r requirements.txt` and restart. |
| `start.bat` shows no public link | Check your internet connection, then run it again. The app still works at http://localhost:5000. |
| `ModuleNotFoundError: No module named 'flask'` | The virtual environment is not active. Run `venv\Scripts\activate` first. |
| Port 5000 already in use | Change the port in `app.py`: `app.run(port=5001)` |

YouTube changes often. If downloads start failing, first update yt-dlp: bump its version in `requirements.txt`, then redeploy.

---

## Dependencies

| Package | Purpose |
|---|---|
| Flask | Web framework; serves the UI and API |
| flask-cors | Cross-Origin Resource Sharing headers |
| yt-dlp[default,deno] | YouTube downloading engine, JS challenge solver and Deno runtime |
| imageio-ffmpeg | Bundled FFmpeg binary for merging video and audio |
| waitress | Production WSGI server that works on Windows |

---

## Legal Notice

This tool is intended for **personal, offline use** of content you have the right to download. Downloading copyrighted content without permission may violate YouTube's Terms of Service and local copyright laws. Use responsibly.
