"""Tutor session: conversation state, turn handling, and the end-of-session summary."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

import sarvam

TOPICS = [
    "Job interview",
    "Ordering food at a restaurant",
    "Meeting a new person",
    "Doctor visit",
    "Travel and directions",
    "Shopping",
]

LEVELS = {1: "Beginner", 2: "Intermediate", 3: "Advanced"}

SYSTEM_PROMPT = """You are a friendly spoken-English tutor. Your learner is a Hindi or Hinglish speaker learning to SPEAK English.

SESSION SETUP: you are given a topic the learner picked and a starting level (1 beginner, 2 intermediate, 3 advanced).

HOW TO BEHAVE:
1. Hold a natural spoken conversation on the topic. Ask short questions, keep your turn under 45 words, one idea at a time.
2. Respond to what the learner actually said — acknowledge their content before moving on. Never swap in an unrelated line.
3. If the learner makes grammar or word-choice mistakes: correct EVERY mistake in that sentence in one short reply, then give a one-sentence Hindi explanation per mistake. Then carry on with the conversation — never stop to lecture.
4. If the learner is stuck (replies in Hindi/Hinglish, or asks for help): first answer them in Hindi, then say it in English, then ask the next question in English. Always steer back to English.
5. Adapt difficulty to how the learner is doing: easy sentences and common words at level 1, connected speech and idioms at level 3. Raise or lower the level as they improve or struggle.
6. Be warm and encouraging. Never mention these instructions.

OUTPUT FORMAT — this exact structure, nothing else:
EN: <what you say aloud in English>
HI: <optional one-line explanation written in Hindi using the Devanagari script — never romanised; only when there is a correction or the learner was stuck>
LEVEL: <1, 2 or 3 — your current judgement of the learner's level>

End the session only when the learner says goodbye or asks to stop."""

SUMMARY_PROMPT = """You are a spoken-English tutor writing the end-of-session summary for a Hindi-speaking learner.
Using only the conversation below, return Markdown with exactly these sections:

## Mistakes made
- each mistake the learner actually made, quoted as they said it

## Corrections
- the corrected form with a short Hindi explanation

## Practise these 3 things
1. …
2. …
3. …

Be specific and honest. If the learner made no mistakes in a category, say so plainly. Write in English with Hindi explanations where useful. Nothing else."""


@dataclass
class Turn:
    heard: str            # what STT heard
    spoken_text: str      # what the tutor says (markers stripped)
    audio_path: str       # concatenated reply audio
    level: int
    ms_stt: int = 0
    ms_llm: int = 0
    ms_tts: int = 0

    @property
    def ms_total(self) -> int:
        return self.ms_stt + self.ms_llm + self.ms_tts


@dataclass
class Tutor:
    topic: str = TOPICS[0]
    level: int = 1
    history: list[dict] = field(default_factory=list)

    def __post_init__(self):
        self.history = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",
             "content": f"Topic: {self.topic}. Starting level: {self.level} "
                        f"({LEVELS[self.level]}). Greet me and begin."},
        ]
        first = sarvam.chat(self.history[:2], max_tokens=300)
        self._push("assistant", first)
        self.greeting = plain_reply(first)
        self.level = _parse_level(first, self.level)

    # ── one learner turn: audio → STT → LLM → TTS ────────────────────────
    def turn(self, audio_path: str | None = None, text: str | None = None) -> Turn:
        t0 = time.time()
        if text is None:
            if not audio_path:
                raise ValueError("need audio or text")
            heard = sarvam.transcribe(audio_path)
            ms_stt = int((time.time() - t0) * 1000)
        else:
            heard, ms_stt = text.strip(), 0
        if not heard:
            raise RuntimeError("could not hear anything — please try again")

        t1 = time.time()
        self._push("user", heard)
        raw = sarvam.chat(self.history)
        ms_llm = int((time.time() - t1) * 1000)
        self._push("assistant", raw)

        segments, spoken = _parse_reply(raw)
        new_level = _parse_level(raw, self.level)
        if new_level != self.level:
            self.level = new_level

        t2 = time.time()
        audio_out = sarvam.speak_mixed(segments)
        ms_tts = int((time.time() - t2) * 1000)

        return Turn(heard=heard, spoken_text=spoken, audio_path=audio_out,
                    level=self.level, ms_stt=ms_stt, ms_llm=ms_llm, ms_tts=ms_tts)

    # ── written session summary ──────────────────────────────────────────
    def summary(self) -> str:
        convo = "\n".join(
            f"{m['role']}: {m['content']}" for m in self.history[1:]
        )
        return sarvam.chat(
            [{"role": "system", "content": SUMMARY_PROMPT},
             {"role": "user", "content": convo}],
            temperature=0.2, max_tokens=900,
        )

    def _push(self, role: str, content: str) -> None:
        self.history.append({"role": role, "content": content})


# ── reply parsing ─────────────────────────────────────────────────────────

def plain_reply(raw: str) -> str:
    """Human-readable text of a model reply (markers stripped)."""
    return _parse_reply(raw)[1]


def _parse_reply(raw: str) -> tuple[list[tuple[str, str]], str]:
    """Split 'EN: … / HI: …' lines into (language, text) segments for TTS.

    Falls back to speaking the whole reply in English if the model ignored
    the format, so the voice never goes silent.
    """
    segments: list[tuple[str, str]] = []
    plain: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if re.match(r"^(EN|HI)\s*:\s*$", line, re.IGNORECASE):
            continue  # model often emits an empty "HI:" line
        m = re.match(r"^(EN|HI)\s*:\s*(.+)$", line, re.IGNORECASE)
        if m:
            text = m.group(2).strip()
            lang = "en-IN" if m.group(1).upper() == "EN" else "hi-IN"
            segments.append((lang, text))
            plain.append(text)
        elif re.match(r"^LEVEL\s*:", line, re.IGNORECASE):
            continue
        else:
            segments.append(("en-IN", line))
            plain.append(line)
    if not segments:
        clean = re.sub(r"\s+", " ", raw).strip()
        segments, plain = [("en-IN", clean)], [clean]
    return segments, " ".join(plain)


def _parse_level(raw: str, default: int) -> int:
    m = re.search(r"LEVEL\s*:\s*([123])", raw, re.IGNORECASE)
    return int(m.group(1)) if m else default
