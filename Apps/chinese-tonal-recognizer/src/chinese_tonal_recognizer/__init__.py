from __future__ import annotations

import argparse
import json
import wave
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

MS_TO_SECONDS = 1000.0
MIN_RMS_THRESHOLD = 1e-4
AUTOCORR_THRESHOLD = 0.22

NEUTRAL_MIN_DURATION_S = 0.18
NEUTRAL_MIN_RANGE_LOG2 = 0.12
LEVEL_MAX_DELTA_LOG2 = 0.08
LEVEL_MAX_RANGE_LOG2 = 0.26
VALLEY_MARGIN_LOG2 = 0.05
VALLEY_MIN_RANGE_LOG2 = 0.2
RISING_DELTA_LOG2 = 0.1
FALLING_DELTA_LOG2 = -0.1


@dataclass
class ToneSegment:
    index: int
    start: float
    end: float
    duration: float
    tone: int
    label: str
    confidence: float
    mean_f0_hz: float
    f0_range_semitones: float


TONE_LABELS: dict[int, str] = {
    1: "high-level",
    2: "rising",
    3: "dipping",
    4: "falling",
    5: "neutral",
}


class AudioFormatError(Exception):
    """Raised when the WAV format is unsupported."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="chinese-tonal-recognizer",
        description="Recognize Mandarin tone contours from spoken WAV audio.",
    )
    parser.add_argument("audio", type=Path, help="Path to a PCM WAV recording")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("tone_segments.json"),
        help="Output JSON file path (default: tone_segments.json)",
    )
    parser.add_argument("--frame-ms", type=float, default=30.0, help="Frame length in ms")
    parser.add_argument("--hop-ms", type=float, default=10.0, help="Hop length in ms")
    parser.add_argument("--min-f0", type=float, default=75.0, help="Minimum pitch (Hz)")
    parser.add_argument("--max-f0", type=float, default=400.0, help="Maximum pitch (Hz)")
    parser.add_argument(
        "--energy-threshold",
        type=float,
        default=0.08,
        help="Relative RMS threshold for voiced detection",
    )
    parser.add_argument(
        "--min-segment-ms",
        type=float,
        default=140.0,
        help="Minimum voiced segment duration in ms",
    )
    return parser.parse_args(argv)


def read_wav_mono(path: Path) -> tuple[np.ndarray, int]:
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    with wave.open(str(path), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        frame_count = wav_file.getnframes()
        raw = wav_file.readframes(frame_count)

    if sample_width not in {1, 2, 4}:
        raise AudioFormatError(f"Unsupported sample width: {sample_width} bytes")

    if sample_width == 1:
        audio = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        audio = (audio - 128.0) / 128.0
    elif sample_width == 2:
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    else:
        audio = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0

    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)

    peak = float(np.max(np.abs(audio))) if audio.size else 0.0
    if peak > 0.0:
        audio = audio / peak

    return audio, sample_rate


def estimate_pitch_hz(frame: np.ndarray, sample_rate: int, min_f0: float, max_f0: float) -> float:
    frame = frame - np.mean(frame)
    rms = float(np.sqrt(np.mean(frame**2)))
    if rms < MIN_RMS_THRESHOLD:
        return float("nan")

    frame = frame * np.hamming(len(frame))
    autocorr = np.correlate(frame, frame, mode="full")[len(frame) - 1 :]

    lag_min = max(1, int(sample_rate / max_f0))
    lag_max = min(len(autocorr) - 1, int(sample_rate / min_f0))
    if lag_max <= lag_min:
        return float("nan")

    roi = autocorr[lag_min : lag_max + 1]
    if roi.size == 0:
        return float("nan")

    best_rel_lag = int(np.argmax(roi))
    best_lag = lag_min + best_rel_lag
    peak = float(autocorr[best_lag])
    energy = float(autocorr[0])

    if energy <= 0.0 or peak / energy < AUTOCORR_THRESHOLD:
        return float("nan")

    return float(sample_rate / best_lag)


def f0_track(
    audio: np.ndarray,
    sample_rate: int,
    frame_ms: float,
    hop_ms: float,
    min_f0: float,
    max_f0: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    frame_size = max(1, int(sample_rate * frame_ms / MS_TO_SECONDS))
    hop_size = max(1, int(sample_rate * hop_ms / MS_TO_SECONDS))

    if len(audio) < frame_size:
        return np.array([]), np.array([]), np.array([])

    f0_values: list[float] = []
    rms_values: list[float] = []
    times: list[float] = []

    for start in range(0, len(audio) - frame_size + 1, hop_size):
        frame = audio[start : start + frame_size]
        f0_values.append(estimate_pitch_hz(frame, sample_rate, min_f0, max_f0))
        rms_values.append(float(np.sqrt(np.mean(frame**2))))
        center = start + frame_size // 2
        times.append(center / sample_rate)

    return np.array(times), np.array(f0_values), np.array(rms_values)


def close_small_gaps(mask: np.ndarray, gap_frames: int = 2) -> np.ndarray:
    """Fill short unvoiced gaps between voiced frames to avoid over-splitting segments."""
    closed = mask.copy()
    i = 0
    while i < len(mask):
        if closed[i]:
            i += 1
            continue
        start = i
        while i < len(mask) and not closed[i]:
            i += 1
        end = i
        if start > 0 and end < len(mask) and (end - start) <= gap_frames:
            closed[start:end] = True
    return closed


def voiced_segments(mask: np.ndarray, min_frames: int) -> list[tuple[int, int]]:
    segments: list[tuple[int, int]] = []
    i = 0
    while i < len(mask):
        if not mask[i]:
            i += 1
            continue
        start = i
        while i < len(mask) and mask[i]:
            i += 1
        end = i
        if (end - start) >= min_frames:
            segments.append((start, end))
    return segments


def classify_tone(segment_f0: np.ndarray, duration: float) -> tuple[int, float]:
    """Classify one voiced segment into Mandarin tone (1-5) and confidence (0-1).

    Heuristics use log-pitch contour shape:
    - tone 1: mostly level
    - tone 2: rising
    - tone 3: dipping/valley
    - tone 4: falling
    - tone 5: short or low-variation neutral contour
    """
    log_f0 = np.log2(segment_f0)
    t = np.linspace(0.0, 1.0, num=len(log_f0))

    early = float(np.mean(log_f0[: max(1, len(log_f0) // 3)]))
    late = float(np.mean(log_f0[-max(1, len(log_f0) // 3) :]))
    mid_start = len(log_f0) // 3
    mid_end = max(mid_start + 1, 2 * len(log_f0) // 3)
    middle = float(np.mean(log_f0[mid_start:mid_end]))

    delta = late - early
    f0_range = float(np.max(log_f0) - np.min(log_f0))

    if duration < NEUTRAL_MIN_DURATION_S or f0_range < NEUTRAL_MIN_RANGE_LOG2:
        return 5, 0.55

    if abs(delta) < LEVEL_MAX_DELTA_LOG2 and f0_range < LEVEL_MAX_RANGE_LOG2:
        confidence = float(np.clip(0.9 - abs(delta) * 2.0 - f0_range, 0.5, 0.95))
        return 1, confidence

    has_valley_contour = middle + VALLEY_MARGIN_LOG2 < min(early, late)
    if has_valley_contour and f0_range > VALLEY_MIN_RANGE_LOG2:
        confidence = float(np.clip(0.6 + f0_range, 0.55, 0.95))
        return 3, confidence

    if delta > RISING_DELTA_LOG2:
        confidence = float(np.clip(0.6 + delta + (f0_range * 0.25), 0.55, 0.95))
        return 2, confidence

    if delta < FALLING_DELTA_LOG2:
        confidence = float(np.clip(0.6 + abs(delta) + (f0_range * 0.2), 0.55, 0.95))
        return 4, confidence

    return 1, 0.5


def analyze_tones(
    audio: np.ndarray,
    sample_rate: int,
    frame_ms: float,
    hop_ms: float,
    min_f0: float,
    max_f0: float,
    energy_threshold: float,
    min_segment_ms: float,
) -> list[ToneSegment]:
    times, f0_values, rms_values = f0_track(audio, sample_rate, frame_ms, hop_ms, min_f0, max_f0)
    if len(times) == 0:
        return []

    max_rms = float(np.max(rms_values)) if len(rms_values) else 0.0
    voiced = np.isfinite(f0_values)
    energetic = rms_values >= (max_rms * energy_threshold if max_rms > 0 else 0)
    mask = close_small_gaps(voiced & energetic)

    hop_seconds = hop_ms / MS_TO_SECONDS
    min_frames = max(1, int((min_segment_ms / MS_TO_SECONDS) / hop_seconds))

    segments = voiced_segments(mask, min_frames=min_frames)
    result: list[ToneSegment] = []

    for idx, (start_idx, end_idx) in enumerate(segments):
        segment_f0 = f0_values[start_idx:end_idx]
        segment_f0 = segment_f0[np.isfinite(segment_f0)]
        if len(segment_f0) < 4:
            continue

        start_time = float(times[start_idx])
        end_time = float(times[end_idx - 1])
        duration = max(0.0, end_time - start_time)

        tone, confidence = classify_tone(segment_f0, duration)
        log_range = float(np.log2(np.max(segment_f0)) - np.log2(np.min(segment_f0)))

        result.append(
            ToneSegment(
                index=idx,
                start=round(start_time, 3),
                end=round(end_time, 3),
                duration=round(duration, 3),
                tone=tone,
                label=TONE_LABELS[tone],
                confidence=round(confidence, 3),
                mean_f0_hz=round(float(np.mean(segment_f0)), 3),
                f0_range_semitones=round(log_range * 12.0, 3),
            )
        )

    return result


def main() -> None:
    args = parse_args()

    if args.min_f0 <= 0 or args.max_f0 <= args.min_f0:
        raise SystemExit("Invalid pitch bounds: ensure 0 < min-f0 < max-f0")
    if args.frame_ms <= 0 or args.hop_ms <= 0:
        raise SystemExit("Invalid frame/hop settings: frame-ms and hop-ms must be positive")

    try:
        audio, sample_rate = read_wav_mono(args.audio)
    except (FileNotFoundError, wave.Error, AudioFormatError) as exc:
        raise SystemExit(f"Audio input error: {exc}") from exc

    segments = analyze_tones(
        audio=audio,
        sample_rate=sample_rate,
        frame_ms=args.frame_ms,
        hop_ms=args.hop_ms,
        min_f0=args.min_f0,
        max_f0=args.max_f0,
        energy_threshold=args.energy_threshold,
        min_segment_ms=args.min_segment_ms,
    )

    payload = {
        "source": str(args.audio),
        "sample_rate": sample_rate,
        "frame_ms": args.frame_ms,
        "hop_ms": args.hop_ms,
        "segments": [asdict(segment) for segment in segments],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Saved {len(segments)} tone segments to {args.output}")


if __name__ == "__main__":
    main()
