## chinese-tonal-recognizer

Recognize Mandarin tone categories from a person's spoken speech in a WAV file.

### What this does

- Reads mono/stereo PCM `.wav` speech audio
- Estimates per-frame pitch with autocorrelation
- Splits voiced regions into speech-tone segments
- Classifies each segment as Tone 1, 2, 3, 4, or Neutral (5)
- Exports JSON with timing and confidence per detected segment

### Requirements

- Python 3.11+
- `uv` installed: https://docs.astral.sh/uv/

### Setup

```powershell
uv sync
```

### Run

```powershell
uv run chinese-tonal-recognizer input.wav
```

This creates `tone_segments.json` in the current folder.

### Useful options

```powershell
# Write output to custom path
uv run chinese-tonal-recognizer input.wav --output data/tones.json

# Tune pitch range for your speaker
uv run chinese-tonal-recognizer input.wav --min-f0 80 --max-f0 380

# Adjust analysis windows
uv run chinese-tonal-recognizer input.wav --frame-ms 30 --hop-ms 10
```

### Output shape

```json
{
  "source": "input.wav",
  "sample_rate": 16000,
  "frame_ms": 30.0,
  "hop_ms": 10.0,
  "segments": [
    {
      "index": 0,
      "start": 0.41,
      "end": 0.73,
      "duration": 0.32,
      "tone": 4,
      "label": "falling",
      "confidence": 0.84,
      "mean_f0_hz": 182.7,
      "f0_range_semitones": 4.8
    }
  ]
}
```

### Notes

- Best results come from clean recordings with one syllable per segment.
- Tone classification is heuristic pitch-contour analysis, not a full ASR model.
