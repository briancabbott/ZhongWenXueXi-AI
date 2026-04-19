from __future__ import annotations

import argparse
import json
import random
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from Pinyin2Hanzi import DefaultHmmParams, viterbi
from pypinyin import Style, lazy_pinyin

HANZI_RE = re.compile(r"[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]")
DEFAULT_DATA_FILE = Path("rememberwords_data.json")


@dataclass
class WordEntry:
    hanzi: str
    pinyin: str
    attempts: int = 0
    correct: int = 0


def load_words(data_file: Path) -> list[WordEntry]:
    if not data_file.exists():
        return []

    payload = json.loads(data_file.read_text(encoding="utf-8"))
    words = payload.get("words", [])
    return [WordEntry(**word) for word in words]


def save_words(data_file: Path, words: list[WordEntry]) -> None:
    data_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {"words": [asdict(word) for word in words]}
    data_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def has_hanzi(value: str) -> bool:
    return bool(HANZI_RE.search(value))


def normalize_pinyin(value: str) -> str:
    lowered = value.lower().replace("ü", "v")
    return re.sub(r"[^a-z0-9]", "", lowered)


def pinyin_from_hanzi(hanzi: str) -> str:
    syllables = lazy_pinyin(hanzi, style=Style.TONE3, neutral_tone_with_five=True)
    return " ".join(syllables)


def hanzi_candidates_from_pinyin(pinyin_input: str, max_results: int = 5) -> list[str]:
    cleaned = pinyin_input.strip().lower()
    if not cleaned:
        return []

    syllables = [piece for piece in re.split(r"[\s'-]+", cleaned) if piece]
    if not syllables:
        return []

    params = DefaultHmmParams()
    results = viterbi(params, syllables, path_num=max_results)
    return ["".join(item.path) for item in results]


def add_word(words: list[WordEntry], raw_input: str, provided_hanzi: str | None = None) -> WordEntry:
    text = raw_input.strip()
    if not text:
        raise ValueError("Word cannot be empty.")

    if has_hanzi(text):
        hanzi = text
        pinyin = pinyin_from_hanzi(hanzi)
    else:
        pinyin = " ".join(part for part in re.split(r"\s+", text.lower()) if part)
        if provided_hanzi:
            hanzi = provided_hanzi.strip()
        else:
            candidates = hanzi_candidates_from_pinyin(pinyin)
            if not candidates:
                raise ValueError("Could not find Hanzi for that pinyin. Use --hanzi to provide it.")
            hanzi = candidates[0]

    if any(word.hanzi == hanzi and word.pinyin == pinyin for word in words):
        raise ValueError("This word is already in your list.")

    entry = WordEntry(hanzi=hanzi, pinyin=pinyin)
    words.append(entry)
    return entry


def run_flashcards(words: list[WordEntry]) -> None:
    if not words:
        print("No words found. Add words first.")
        return

    cards = words[:]
    random.shuffle(cards)
    print("Flashcards started. Press Enter to reveal answers. Type q to stop.")
    for card in cards:
        front = input(f"\nHanzi: {card.hanzi}\nPress Enter to reveal pinyin (or q to quit): ").strip().lower()
        if front == "q":
            break
        print(f"Pinyin: {card.pinyin}")


def run_quiz(words: list[WordEntry], count: int) -> None:
    if not words:
        print("No words found. Add words first.")
        return

    if count <= 0:
        raise ValueError("Quiz count must be positive.")

    prompts = random.sample(words, k=min(count, len(words)))
    correct_answers = 0

    print("Quiz started. Answer using pinyin or Hanzi based on the prompt.")
    for word in prompts:
        ask_for_pinyin = random.choice([True, False])
        if ask_for_pinyin:
            answer = input(f"\nHanzi: {word.hanzi}\nPinyin: ").strip()
            is_correct = normalize_pinyin(answer) == normalize_pinyin(word.pinyin)
        else:
            answer = input(f"\nPinyin: {word.pinyin}\nHanzi: ").strip()
            is_correct = answer == word.hanzi

        word.attempts += 1
        if is_correct:
            word.correct += 1
            correct_answers += 1
            print("✅ Correct")
        else:
            print(f"❌ Incorrect. Correct answer: {word.pinyin if ask_for_pinyin else word.hanzi}")

    percent = (correct_answers / len(prompts)) * 100
    print(f"\nQuiz complete: {correct_answers}/{len(prompts)} correct ({percent:.1f}%)")


def print_stats(words: list[WordEntry]) -> None:
    if not words:
        print("No words found. Add words first.")
        return

    total_attempts = sum(word.attempts for word in words)
    total_correct = sum(word.correct for word in words)
    overall = (total_correct / total_attempts * 100) if total_attempts else 0.0

    print(f"Overall remembrance rate: {overall:.1f}% ({total_correct}/{total_attempts})")
    print("Per-word rates:")
    for word in words:
        rate = (word.correct / word.attempts * 100) if word.attempts else 0.0
        print(f"- {word.hanzi} ({word.pinyin}): {rate:.1f}% ({word.correct}/{word.attempts})")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="rememberwords",
        description="Study Chinese words with Hanzi↔Pinyin lookup, flashcards, and quizzes.",
    )
    parser.add_argument(
        "--data-file",
        type=Path,
        default=DEFAULT_DATA_FILE,
        help="JSON file used to store your words and quiz progress.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Add a word using Hanzi or pinyin input")
    add_parser.add_argument("word", help="Hanzi text or pinyin text")
    add_parser.add_argument("--hanzi", help="Optional Hanzi override when adding from pinyin")

    subparsers.add_parser("list", help="List saved words")
    subparsers.add_parser("flashcards", help="Run flashcard study mode")

    quiz_parser = subparsers.add_parser("quiz", help="Run a quiz and track remembrance rate")
    quiz_parser.add_argument("--count", type=int, default=10, help="Number of quiz questions")

    subparsers.add_parser("stats", help="Show remembrance statistics")

    return parser.parse_args(argv)


def main() -> None:
    args = parse_args(sys.argv[1:])
    words = load_words(args.data_file)

    try:
        if args.command == "add":
            entry = add_word(words, args.word, args.hanzi)
            save_words(args.data_file, words)
            print(f"Added: {entry.hanzi} ↔ {entry.pinyin}")
            if not has_hanzi(args.word):
                candidates = hanzi_candidates_from_pinyin(args.word)
                if candidates:
                    print(f"Top Hanzi candidates: {', '.join(candidates)}")

        elif args.command == "list":
            if not words:
                print("No words found. Add words first.")
            else:
                for idx, word in enumerate(words, start=1):
                    print(f"{idx}. {word.hanzi} ↔ {word.pinyin}")

        elif args.command == "flashcards":
            run_flashcards(words)

        elif args.command == "quiz":
            run_quiz(words, args.count)
            save_words(args.data_file, words)

        elif args.command == "stats":
            print_stats(words)
    except ValueError as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
