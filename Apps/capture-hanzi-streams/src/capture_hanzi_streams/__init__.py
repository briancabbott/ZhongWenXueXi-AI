from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlparse

from opencc import OpenCC
from youtube_transcript_api import (
    CouldNotRetrieveTranscript,
    NoTranscriptFound,
    Transcript,
    TranscriptList,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApi,
)

PREFERRED_SIMPLIFIED_CODES = ("zh-Hans", "zh-CN", "zh-SG", "zh")
HANZI_RE = re.compile(r"[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]")


class SimplifiedChineseTranscriptUnavailable(Exception):
    """Raised when Simplified Chinese subtitles cannot be found or translated."""


@dataclass
class Segment:
    index: int
    start: float
    end: float
    duration: float
    text: str


def extract_video_id(url_or_id: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url_or_id):
        return url_or_id

    parsed = urlparse(url_or_id)
    host = parsed.netloc.lower()

    if "youtu.be" in host:
        return parsed.path.strip("/").split("/")[0]

    if "youtube.com" in host:
        query_video_id = parse_qs(parsed.query).get("v")
        if query_video_id:
            return query_video_id[0]

        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2 and parts[0] in {"shorts", "embed", "live", "v"}:
            return parts[1]

    raise ValueError(
        "Could not parse a YouTube video ID from input. Provide a full URL or 11-char video ID."
    )


def pick_transcript(transcript_list: TranscriptList) -> tuple[Transcript, bool, bool]:
    for finder in (
        transcript_list.find_manually_created_transcript,
        transcript_list.find_generated_transcript,
        transcript_list.find_transcript,
    ):
        try:
            return finder(PREFERRED_SIMPLIFIED_CODES), False, False
        except NoTranscriptFound:
            continue

    for transcript in transcript_list:
        if transcript.is_translatable:
            translation_codes = {lang.language_code for lang in transcript.translation_languages}

            for code in PREFERRED_SIMPLIFIED_CODES:
                if code in translation_codes:
                    try:
                        return transcript.translate(code), True, False
                    except Exception:
                        continue

            if "zh-Hant" in translation_codes:
                try:
                    return transcript.translate("zh-Hant"), True, True
                except Exception:
                    continue

            try:
                return transcript.translate("zh-Hans"), True, False
            except Exception:
                continue

    raise SimplifiedChineseTranscriptUnavailable(
        "No Simplified Chinese transcript was found and translation to zh-Hans failed."
    )


def extract_hanzi(text: str) -> str:
    return "".join(HANZI_RE.findall(text))


def build_segments(
    raw_segments: list[dict],
    hanzi_only: bool,
    include_empty: bool,
    text_transform: Callable[[str], str] | None = None,
) -> list[Segment]:
    segments: list[Segment] = []

    for idx, item in enumerate(raw_segments):
        original_text = item["text"].strip()
        if text_transform is not None:
            original_text = text_transform(original_text)

        text = extract_hanzi(original_text) if hanzi_only else original_text
        if not text and not include_empty:
            continue

        start = float(item["start"])
        duration = float(item["duration"])
        segments.append(
            Segment(
                index=idx,
                start=start,
                end=start + duration,
                duration=duration,
                text=text,
            )
        )

    return segments


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="capture-hanzi-streams",
        description=(
            "Download YouTube captions in Simplified Chinese and export time-segmented text. "
            "If no Simplified Chinese track exists, the script attempts auto-translation to zh-Hans."
        ),
    )
    parser.add_argument("url", help="YouTube video URL or 11-character video ID")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("segments.json"),
        help="Output JSON file path (default: segments.json)",
    )
    parser.add_argument(
        "--hanzi-only",
        action="store_true",
        help="Keep only Hanzi characters in each segment's text",
    )
    parser.add_argument(
        "--include-empty",
        action="store_true",
        help="Include empty text segments (default: skipped)",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args(sys.argv[1:])

    try:
        video_id = extract_video_id(args.url)
        transcript_list = YouTubeTranscriptApi().list(video_id)
        transcript, was_translated, converted_from_traditional = pick_transcript(transcript_list)
        fetched = transcript.fetch(preserve_formatting=False)
        text_transform = OpenCC("t2s").convert if converted_from_traditional else None

        segments = build_segments(
            fetched.to_raw_data(),
            hanzi_only=args.hanzi_only,
            include_empty=args.include_empty,
            text_transform=text_transform,
        )
    except ValueError as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    except (
        VideoUnavailable,
        TranscriptsDisabled,
        CouldNotRetrieveTranscript,
        NoTranscriptFound,
        SimplifiedChineseTranscriptUnavailable,
    ) as exc:
        print(f"Transcript error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    payload = {
        "video_id": video_id,
        "source": args.url,
        "requested_language": "zh-Hans",
        "selected_language_code": transcript.language_code,
        "selected_language": transcript.language,
        "translated": was_translated,
        "converted_traditional_to_simplified": converted_from_traditional,
        "segments": [asdict(segment) for segment in segments],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        f"Saved {len(segments)} segments to {args.output} "
        f"(language={transcript.language_code}, translated={was_translated}, "
        f"t2s={converted_from_traditional})."
    )
