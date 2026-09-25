# YouTube Video Downloader

A modern, browser-based YouTube video downloader built with Flask and yt-dlp. Paste a URL, pick a resolution, and the video downloads through your browser. It runs locally or on Vercel.

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

## Deploy to Vercel

1. Push this repo to GitHub.
2. On [vercel.com/new](https://vercel.com/new), import the repo. Vercel detects Flask from the top-level `app` in `app.py`, so leave **Framework Preset**, build command and output directory at their defaults.
3. Click **Deploy**.
4. Open `https://<your-project>.vercel.app/health`. It should report `"deno": true, "ffmpeg": true`.

Or use the CLI: `npm i -g vercel`, then run `vercel` (preview) or `vercel --prod` from the project folder.

### Limits on Vercel

- **Duration:** each download must finish within the function time limit: 300 s on Hobby, up to 800 s on Pro. Long videos at 1080p may time out. Use a lower resolution, or run the app locally.
- **YouTube bot check:** YouTube often blocks data-center IPs, including Vercel's, with *"Sign in to confirm you're not a bot"*. If you see this, add one of these **Environment Variables** in Vercel (Project → Settings → Environment Variables), then redeploy:

| Variable | Value |
|---|---|
| `YTDLP_COOKIES` | Full contents of a Netscape-format `cookies.txt` exported from a browser logged in to YouTube. Use a throwaway Google account. |
| `YTDLP_PROXY` | A proxy URL, e.g. `http://user:pass@host:port` (a residential proxy works best). |

For heavy use, a regular server works better than serverless because it has no time limit and a stable IP. Good options are a VPS, Render, Railway or Fly.io; there, run `gunicorn app:app`.

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
├── app.py              # Flask backend (API + serves frontend); `app` is the Vercel entry point
├── requirements.txt    # Python dependencies
├── .vercelignore       # Files excluded from the Vercel upload
└── templates/
    └── index.html      # Single-page frontend
```

---

## API Endpoints

| Method | Endpoint    | Description                                          |
|--------|-------------|------------------------------------------------------|
| GET    | `/`         | Serves the web UI                                    |
| GET    | `/health`   | Health check, yt-dlp version, deno/ffmpeg found      |
| POST   | `/get-info` | Fetch video metadata and resolutions                 |
| POST   | `/download` | Download the video and stream the MP4 in the response |

```json
// /get-info
{ "url": "https://www.youtube.com/watch?v=..." }

// /download
{ "url": "https://www.youtube.com/watch?v=...", "resolution": "720p" }
```

Errors are returned as `{ "error": "..." }` with HTTP 400.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `This video is not available` for a working video | yt-dlp is outdated or has no JS runtime. Run `pip install -U -r requirements.txt`. |
| `Sign in to confirm you're not a bot` | YouTube is blocking the server's IP. Set `YTDLP_COOKIES` or `YTDLP_PROXY` (see above). |
| `FUNCTION_INVOCATION_TIMEOUT` on Vercel | The video is too long for the time limit. Pick a lower resolution. |
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

---

## Legal Notice

This tool is intended for **personal, offline use** of content you have the right to download. Downloading copyrighted content without permission may violate YouTube's Terms of Service and local copyright laws. Use responsibly.
