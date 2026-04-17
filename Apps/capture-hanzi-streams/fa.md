Implemented a new uv-based Python project in capture-hanzi-streams that captures YouTube closed-caption segments in Simplified Chinese and exports them with timestamps.

What I changed:
1. Project scaffolded with uv and dependencies added in pyproject.toml
2. Full CLI implementation added in __init__.py
3. Usage and behavior documented in README.md
4. Lockfile generated at uv.lock

Implemented behavior:
1. Accepts a YouTube URL or 11-character video ID
2. Prioritizes Simplified caption tracks: zh-Hans, zh-CN, zh-SG, zh
3. If not available, tries translation from another transcript
4. If only Traditional translation is available (zh-Hant), converts to Simplified using OpenCC
5. Outputs segment-by-segment JSON with:
- index
- start
- end
- duration
- text

CLI options included:
1. --output to choose output file
2. --hanzi-only to keep only Hanzi characters
3. --include-empty to retain empty segments

Validation status:
1. Entry point and arguments verified successfully via help command
2. Live transcript fetch in this environment is currently blocked by YouTube IP restrictions, so full network fetch could not be confirmed here

Run it:
1. Ensure uv is available in your shell (installer put it at bin)
2. From capture-hanzi-streams:
- uv sync
- uv run capture-hanzi-streams "https://www.youtube.com/watch?v=VIDEO_ID"

Natural next steps:
1. If you want, I can add a second exporter format (JSONL or CSV) for easier downstream model ingestion.
2. I can also add retry/proxy/cookie support to improve success rate when YouTube blocks transcript requests.