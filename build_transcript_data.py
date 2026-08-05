#!/usr/bin/env python3
"""Convert YouTube karaoke-style VTT captions into browser-ready timed words."""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path


TIMESTAMP = re.compile(r"(\d{2}):(\d{2}):(\d{2})\.(\d{3})")
CUE = re.compile(
    r"^(\d{2}:\d{2}:\d{2}\.\d{3})\s+-->\s+(\d{2}:\d{2}:\d{2}\.\d{3})"
)
TIMED_TOKEN = re.compile(
    r"<(\d{2}:\d{2}:\d{2}\.\d{3})><c(?:\.[^>]*)?>(.*?)</c>"
)
TAG = re.compile(r"<[^>]+>")
STAGE_DIRECTION = re.compile(r"^\[[^\]]+\]$")


def seconds(value: str) -> float:
    match = TIMESTAMP.fullmatch(value)
    if not match:
        raise ValueError(f"Invalid timestamp: {value}")
    hours, minutes, secs, millis = (int(part) for part in match.groups())
    return hours * 3600 + minutes * 60 + secs + millis / 1000


def clean_token(value: str) -> str:
    value = html.unescape(TAG.sub("", value)).strip()
    value = re.sub(r"(^|\s)>>(?=\s|$)", r"\1", value).strip()
    if not value:
        return ""
    value = re.sub(r"\bSouls\b", "Sowell's", value, flags=re.IGNORECASE)
    value = re.sub(
        r"\b(?:Soul|Soell|Seoul|Saul)(?P<possessive>'s)?\b",
        lambda match: "Sowell's" if match.group("possessive") else "Sowell",
        value,
        flags=re.IGNORECASE,
    )
    return value


def parse_words(vtt_text: str) -> list[dict]:
    words: list[dict] = []
    seen: set[tuple[int, str]] = set()

    for block in re.split(r"\n\s*\n", vtt_text):
        lines = block.splitlines()
        if not lines:
            continue
        cue_match = CUE.match(lines[0])
        if not cue_match:
            continue
        cue_start = seconds(cue_match.group(1))

        for line in lines[1:]:
            matches = list(TIMED_TOKEN.finditer(line))
            if not matches:
                continue

            prefix = clean_token(line[: matches[0].start()])
            if prefix and not STAGE_DIRECTION.match(prefix):
                prefix_parts = prefix.split()
                next_start = seconds(matches[0].group(1))
                span = max(0.04, next_start - cue_start)
                for index, token in enumerate(prefix_parts):
                    start = cue_start + (span * index / max(1, len(prefix_parts)))
                    key = (round(start * 1000), token)
                    if key not in seen:
                        words.append({"text": token, "start": round(start, 3)})
                        seen.add(key)

            for match in matches:
                token = clean_token(match.group(2))
                if not token or STAGE_DIRECTION.match(token):
                    continue
                start = seconds(match.group(1))
                key = (round(start * 1000), token)
                if key in seen:
                    continue
                words.append({"text": token, "start": round(start, 3)})
                seen.add(key)

    words.sort(key=lambda word: word["start"])
    for index, word in enumerate(words):
        next_start = words[index + 1]["start"] if index + 1 < len(words) else word["start"] + 0.8
        word["end"] = round(min(next_start, word["start"] + 1.4), 3)
    return words


def make_paragraphs(words: list[dict]) -> list[dict]:
    paragraphs: list[dict] = []
    current: list[dict] = []

    for index, word in enumerate(words):
        current.append(word)
        next_word = words[index + 1] if index + 1 < len(words) else None
        count = len(current)
        sentence_end = bool(re.search(r"[.!?][\"']?$", word["text"]))
        long_gap = bool(next_word and next_word["start"] - word["start"] > 1.7)
        should_break = count >= 120 or (count >= 62 and sentence_end) or (count >= 34 and long_gap)

        if should_break or next_word is None:
            paragraphs.append(
                {
                    "start": current[0]["start"],
                    "end": current[-1]["end"],
                    "words": current,
                }
            )
            current = []

    return paragraphs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vtt", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    vtt = Path(args.vtt).read_text(encoding="utf-8")
    words = parse_words(vtt)
    paragraphs = make_paragraphs(words)
    payload = {
        "title": "Thomas Sowell as Cultural Historian",
        "speakers": "Coleman Hughes, Victor Davis Hanson, and Niall Ferguson",
        "channel": "Hoover Institution",
        "source": "https://youtu.be/XeWGy3fVkK8?is=uBmbGzjHGglgdfOE",
        "paragraphs": paragraphs,
        "wordCount": len(words),
        "transcriptStart": words[0]["start"] if words else 0,
        "transcriptEnd": words[-1]["end"] if words else 0,
    }
    output = "window.TRANSCRIPT_DATA = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n"
    Path(args.out).write_text(output, encoding="utf-8")
    print(
        json.dumps(
            {
                "words": len(words),
                "paragraphs": len(paragraphs),
                "start": payload["transcriptStart"],
                "end": payload["transcriptEnd"],
                "output": args.out,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
