## rememberwords

CLI app for adding Chinese words from Hanzi or pinyin, studying with flashcards, and taking quizzes that track remembrance rate.

### Requirements

- Python 3.11+
- `uv` installed: https://docs.astral.sh/uv/

### Setup

```powershell
uv sync
```

### Run

```powershell
# Add with Hanzi input (auto-generates pinyin)
uv run rememberwords add "你好"

# Add with pinyin input (auto-looks up Hanzi)
uv run rememberwords add "ni hao"

# View saved words
uv run rememberwords list

# Flashcard mode
uv run rememberwords flashcards

# Quiz mode with score tracking
uv run rememberwords quiz --count 10

# Remembrance-rate stats
uv run rememberwords stats
```

### Data storage

By default, study data is written to `rememberwords_data.json` in the current directory.
Use `--data-file` to change the location.
