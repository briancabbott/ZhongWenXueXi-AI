## capture-hanzi-streams

Capture Simplified Chinese subtitle text from a YouTube video, segmented by caption timing.

### What this does

- Accepts a YouTube URL (or video ID)
- Tries to load a Simplified Chinese caption track first (`zh-Hans`, `zh-CN`, `zh-SG`, `zh`)
- If none exists, attempts translation to `zh-Hans` from another available transcript
- If only `zh-Hant` translation is available, converts it to Simplified Chinese
- Exports JSON with `start`, `end`, `duration`, and `text` per segment

### Requirements

- Python 3.11+
- `uv` installed: https://docs.astral.sh/uv/

### Setup

```powershell
uv sync
```

### Run

```powershell
uv run capture-hanzi-streams "https://www.youtube.com/watch?v=VIDEO_ID"
```

This creates `segments.json` in the current folder.

### Useful options

```powershell
# Write output to a custom file
uv run capture-hanzi-streams "https://www.youtube.com/watch?v=VIDEO_ID" --output data/my_segments.json

# Keep only Hanzi characters in each segment
uv run capture-hanzi-streams "https://www.youtube.com/watch?v=VIDEO_ID" --hanzi-only

# Include empty segments too
uv run capture-hanzi-streams "https://www.youtube.com/watch?v=VIDEO_ID" --include-empty
```

### Output shape

```json
{
	"video_id": "...",
	"source": "https://www.youtube.com/watch?v=...",
	"requested_language": "zh-Hans",
	"selected_language_code": "zh-Hans",
	"selected_language": "Chinese (Simplified)",
	"translated": false,
	"converted_traditional_to_simplified": false,
	"segments": [
		{
			"index": 0,
			"start": 1.36,
			"end": 3.04,
			"duration": 1.68,
			"text": "你好"
		}
	]
}
```


Example streams:
https://www.youtube.com/watch?v=9eXyFokrfzY