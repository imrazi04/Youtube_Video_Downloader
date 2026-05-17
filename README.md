# YouTube Video Downloader

A modern, browser-based YouTube video downloader built with Flask and yt-dlp. Paste a URL, pick a resolution, and the video saves directly to your Downloads folder.

---

## Features

- Clean single-page UI with live progress bar
- Supports 360p, 480p, 720p, and 1080p
- Automatic video + audio merging via FFmpeg (for split-stream resolutions)
- Success notification with 5-second auto-reset
- Error display with one-click Retry
- Partial-file cleanup on failed downloads

---

## Prerequisites

### 1 — Python 3.9+

Download from [python.org](https://www.python.org/downloads/). During installation on Windows, check **"Add Python to PATH"**.

Verify:

```bash
python --version
```

### 2 — FFmpeg

FFmpeg is required to merge video and audio streams for 720p / 1080p downloads.

**Windows**

1. Download the latest build from [ffmpeg.org/download.html](https://ffmpeg.org/download.html) (choose a Windows build, e.g. from gyan.dev or BtbN).
2. Extract the zip and copy `ffmpeg.exe`, `ffprobe.exe`, and `ffplay.exe` from the `bin/` folder to a permanent location, e.g. `C:\ffmpeg\bin\`.
3. Add that folder to your **PATH**:
   - Search "Environment Variables" in the Start menu.
   - Under *System Variables* → *Path* → **Edit** → **New** → paste `C:\ffmpeg\bin`.
   - Click OK and restart any open terminals.

**macOS (Homebrew)**

```bash
brew install ffmpeg
```

**Linux (apt)**

```bash
sudo apt update && sudo apt install ffmpeg
```

Verify FFmpeg is available:

```bash
ffmpeg -version
```

---

## Installation

```bash
# 1. Clone or download the project
git clone https://github.com/imrazi04/Youtube_Video_Downloader.git
cd Youtube_Video_Downloader

# 2. Create and activate a virtual environment
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

# 3. Install Python dependencies
pip install -r requirements.txt
```

---

## Running the App

```bash
# Make sure the virtual environment is active, then:
python app.py
```

You should see:

```
 * Running on http://0.0.0.0:5000
```

Open your browser and go to:

```
http://localhost:5000
```

---

## How to Use

1. **Paste** a YouTube video URL into the input field and click **Fetch**.
2. The app retrieves the video title, thumbnail, and available resolutions.
3. **Select** your preferred resolution from the dropdown.
4. Click **Download** — a progress bar shows real-time download speed and percentage.
5. When complete, a success message appears and the UI resets automatically after 5 seconds.
6. If an error occurs, an error message is shown with a **Retry** button or a **Start Over** option.

Downloaded files are saved to your system **Downloads** folder (`~/Downloads`).

> **Note:** Resolutions marked *(requires FFmpeg merge)* are split video+audio streams. FFmpeg must be installed and on PATH for these to work correctly.

---

## Project Structure

```
Youtube_Video_Downloader/
├── app.py                  # Flask backend (API + serves frontend)
├── requirements.txt        # Python dependencies
├── templates/
│   └── index.html          # Single-page frontend (all states)
├── monitor.py              # CLI progress monitor (dev/debug use)
├── venv/                   # Python virtual environment (git-ignored)
└── README.md
```

---

## API Endpoints

| Method | Endpoint    | Description                              |
|--------|-------------|------------------------------------------|
| GET    | `/`         | Serves the web UI                        |
| GET    | `/health`   | Health check + yt-dlp version            |
| POST   | `/get-info` | Fetch video metadata and resolutions     |
| POST   | `/download` | Start a background download              |
| GET    | `/progress` | Poll current download state              |
| POST   | `/reset`    | Manually reset progress to idle          |

### `/get-info` request body

```json
{ "url": "https://www.youtube.com/watch?v=..." }
```

### `/download` request body

```json
{ "url": "https://www.youtube.com/watch?v=...", "resolution": "720p" }
```

### `/progress` response

```json
{
  "status":   "downloading",
  "percent":  " 64.3%",
  "speed":    "3.20MiB/s",
  "filename": "",
  "error":    null
}
```

`status` values: `idle` · `starting` · `downloading` · `finished` · `error`

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'flask'` | Virtual environment not active — run `venv\Scripts\activate` first |
| Progress stays at 0% / video not saved | FFmpeg not on PATH — follow the FFmpeg installation steps above |
| `ERROR: Sign in to confirm your age` | yt-dlp limitation for age-restricted videos |
| Port 5000 already in use | Change the port in `app.py`: `app.run(port=5001)` |
| `.part` file left in Downloads | This is auto-cleaned on failed downloads; manually delete if needed |

---

## Dependencies

| Package | Purpose |
|---|---|
| Flask | Web framework / serves UI and API |
| flask-cors | Cross-Origin Resource Sharing headers |
| yt-dlp | YouTube downloading engine |

---

## Legal Notice

This tool is intended for **personal, offline use** of content you have the right to download. Downloading copyrighted content without permission may violate YouTube's Terms of Service and local copyright laws. Use responsibly.
