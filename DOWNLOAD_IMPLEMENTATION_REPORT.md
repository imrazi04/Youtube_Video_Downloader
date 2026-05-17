# Video Download with Progress Tracking - Implementation Report

## 1. Downloads Folder Path (Cross-Platform)

**Implementation:**
```python
def get_downloads_folder():
    return os.path.join(os.path.expanduser("~"), "Downloads")
```

**Windows:** `C:\Users\<username>\Downloads`  
**macOS:** `/Users/<username>/Downloads`  
**Linux:** `/home/<username>/Downloads`

`os.path.expanduser("~")` resolves to the current user's home directory. Combining it with `"Downloads"` using `os.path.join` ensures correct path separators per OS (`\` on Windows, `/` on Unix).

The path is passed to yt-dlp as `outtmpl`:
```python
output_template = os.path.join(downloads_folder, "%(title)s.%(ext)s")
```
This saves files with the video title as filename, automatically appended with the correct extension.

---

## 2. Format Selection & Video-Audio Merging Logic

### Format Selector String
```python
format_selector = (
    f"bestvideo[height<={target_height}][vcodec!=none][acodec=none]"
    f"+bestaudio[acodec!=none][vcodec=none]"
    f"/best[height<={target_height}]"
)
```

### How it works:

**Part 1 — `bestvideo[height<={target_height}][vcodec!=none][acodec=none]`**
- Selects the best **video-only** stream at or below the requested height
- `vcodec!=none` ensures it has video
- `acodec=none` ensures it's video-only (no audio)

**Part 2 — `+bestaudio[acodec!=none][vcodec=none]`**
- Selects the best **audio-only** stream
- `acodec!=none` ensures it has audio
- `vcodec=none` ensures it's audio-only

**Part 3 — `/best[height<={target_height}]`**
- Fallback: if the video+audio combo isn't available, use the best combined format at or below target height

yt-dlp automatically invokes **ffmpeg** to merge the video-only and audio-only streams into a single file when the `+` operator is used. The merged file is saved as MP4 (specified by `merge_output_format: "mp4"`). No manual merging code is needed — yt-dlp handles it internally as long as ffmpeg is installed and available in PATH.

**Example for 1080p request:**
- If 1080p video-only + best audio exists → merged 1080p MP4
- If only 1080p combined exists → downloaded directly
- If neither, falls back to highest combined format ≤ 1080p (e.g., 720p)

---

## 3. Progress Hook Implementation

### Global State Store
```python
_download_progress = {
    "percent": "",
    "speed": "",
    "status": "idle",  # idle | starting | downloading | finished | error
    "filename": "",
    "error": None,
}
_download_lock = threading.Lock()
```

### Progress Hook Function
```python
def progress_hook(d):
    """yt-dlp progress hook to update global progress state."""
    global _download_progress
    with _download_lock:
        if d["status"] == "downloading":
            _download_progress["status"] = "downloading"
            _download_progress["percent"] = d.get("_percent_str", "N/A")
            _download_progress["speed"] = d.get("_speed_str", "N/A")
            _download_progress["error"] = None
        elif d["status"] == "finished":
            _download_progress["status"] = "finished"
            _download_progress["percent"] = "100%"
            _download_progress["speed"] = ""
            _download_progress["filename"] = d.get("filename", "")
            _download_progress["error"] = None
```

**Hook details:**
- `status == "downloading"`: Extract `_percent_str` (e.g., `"45.2%"`) and `_speed_str` (e.g., `"2.5MiB/s"`) from the hook dict
- `status == "finished"`: Mark complete, store final filename
- `threading.Lock` ensures thread-safe updates from the background download thread

### Integrating into yt-dlp
```python
ydl_opts = {
    ...
    "progress_hooks": [progress_hook],
    "merge_output_format": "mp4",
    "format": format_selector,
}
```

---

## 4. Endpoints

### POST `/download`
```json
Request: {"url": "...", "resolution": "1080p"}
Response (202 Accepted): {
  "message": "Download started",
  "resolution": "1080p",
  "status": "starting"
}
```
- Validates URL and resolution
- Resets progress store
- Spawns a daemon thread running `download_worker()`
- Returns immediately with `202 Accepted`

### GET `/progress`
```json
Response: {
  "percent": "67%",
  "speed": "3.2MiB/s",
  "status": "downloading",
  "filename": "",
  "error": null
}
```
**Status values:** `idle`, `starting`, `downloading`, `finished`, `error`

When `status == "finished"`, `percent` is `"100%"` and `filename` contains the saved file path.

---

## 5. Threading Model

- `download_worker()` runs in a **daemon thread** — doesn't block the Flask responder
- A **global `_download_lock`** (threading.RLock) serializes access to `_download_progress`
- Single global state store is used (suitable for single-user, single-download-at-a-time scenario)
- The `/progress` endpoint reads the same state under the same lock

---

## 6. Error Handling

- Download errors (restricted video, network failure, etc.) caught via `yt_dlp.utils.DownloadError` → progress `status: "error"` with error message
- Generic exceptions also caught → `status: "error"`
- `/progress` returns `error` field with message when failed

---

## Summary

The `/download` endpoint:
1. Accepts `url` + `resolution`
2. Saves to system `Downloads` folder (cross-platform)
3. Uses yt-dlp format selector to auto-merge video+audio via ffmpeg
4. Tracks progress via hook updating thread-safe global state
5. Exposes live progress via `/progress` GET endpoint

**Note:** ffmpeg must be installed and in PATH for merging video-only + audio-only streams. yt-dlp will fail with a clear error if ffmpeg is missing when merge is required. This dependency should be documented in the project README (already standard for yt-dlp projects).
