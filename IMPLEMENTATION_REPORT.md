# Metadata Retrieval Endpoint - Implementation Report

## 1. Sample JSON Response

Endpoint tested: `POST http://localhost:5000/get-info`

Request body:
```json
{
  "url": "https://www.youtube.com/watch?v=jNQXAC9IVRw"
}
```

Response (status 200):
```json
{
  "title": "Me at the zoo",
  "thumbnail": "https://i.ytimg.com/vi/jNQXAC9IVRw/hqdefault.jpg?sqp=-oaymwEmCOADEOgC8quKqQMa8AEB-AG-AoAC8AGKAgwIABABGFUgWShlMA8=&rs=AOn4CLA9eLBatYv9WbkD4BbZ2Im-biSPTw",
  "duration": 19,
  "available_resolutions": ["240p"],
  "video_only_resolutions": ["144p", "240p"],
  "note": "Combined video+audio resolutions are prioritized. Video-only resolutions are returned separately for future merge planning."
}
```

## 2. Resolution Filtering Logic

### Target Resolutions
The endpoint targets these specific resolutions: `["360p", "480p", "720p", "1080p"]`

### Multi-Stage Resolution Extraction

Since yt-dlp returns varied metadata across formats, the code extracts resolution through multiple fallback fields (in order):

1. `format["resolution"]` — explicit resolution string (e.g., "1920x1080")
2. `format["format_note"]` — often contains resolution label (e.g., "720p")
3. `format["format"]` — the display format string
4. `format["height"]` — numeric height value

Integer heights are converted to standard format (e.g., `1080` → `"1080p"`). Regex `r"(360|480|720|1080)p"` is then used to match and normalize resolution strings to the target set.

Only resolutions matching the target list are considered.

## 3. Video+Audio vs Video-Only Format Handling (yt-dlp Specifics)

### yt-dlp Format Structure
Each format dictionary contains:
- `vcodec`: video codec (`"none"` if audio-only)
- `acodec`: audio codec (`"none"` if video-only)

### Classification Logic

```python
has_video = fmt.get("vcodec") and fmt.get("vcodec") != "none"
has_audio = fmt.get("acodec") and fmt.get("acodec") != "none"

if has_video and has_audio:
    → added to video_audio_resolutions
elif has_video and not has_audio:
    → added to video_only_resolutions
```

### Response Strategy

- `available_resolutions`: Combined video+audio formats only (these can be downloaded directly)
- `video_only_resolutions`: Video-only formats at target resolutions (these would require merging with separate audio tracks in a later phase)
- Duplicates are eliminated using membership checks before adding to lists

This separation allows the download phase to prioritize combined formats while keeping video-only options documented for future merge functionality.

## 4. Error Handling

- Invalid/missing JSON body → `400` with `{"error": "Invalid JSON body."}`
- Missing `url` field → `400` with `{"error": "A valid 'url' field is required."}`
- yt-dlp `DownloadError` (invalid URL, restricted video, age-restricted, etc.) → `400` with the error message
- Generic exceptions → `400` with `{"error": "Unable to extract video info: ..."}`

## 5. Implementation Notes

- The endpoint uses `yt_dlp.YoutubeDL` with `download=False` (extract_info mode)
- `skip_download=True` ensures no media is fetched
- `quiet=True` suppresses verbose output
- The `/health` endpoint exposes the yt-dlp version for debugging
