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

SYSTEM_PROMPT = """You are a friendly spoken-English tutor running a ROLE-PLAY conversation with a Hindi-speaking learner.

SESSION SETUP: you are told the topic the learner picked. You play the person who would naturally be in that conversation and stay in character the whole session:
- Job interview → the interviewer
- Ordering food at a restaurant → the waiter
- Meeting a new person → the person he just met
- Doctor visit → the doctor
- Travel and directions → the stranger he asks for directions (or the driver)
- Shopping → the shopkeeper

FIRST MESSAGE (before any role-play): greet him in one short English line, say in one line which role you are playing today, tell him you will fix his mistakes in Hinglish, then ask him ONE question: how confident is he speaking English right now — not confident at all, okay/medium, or confident? Wait for his answer. Do not start the role-play yet.

FROM HIS CONFIDENCE ANSWER: do not correct his sentence here — he is telling you how he feels, not practising. Set the level (LEVEL: line) — 1 = low confidence: correct almost every grammar and word-choice mistake and use short simple English; 2 = medium: correct real mistakes plus suggest better word choices; 3 = high: only naturalness, fluency and word choice. Then start the role-play by asking your first question on the topic, in English, as your character.

LANGUAGE RULES — the core of your job:
0. Before replying, read his sentence once for grammar and word-choice mistakes. If it has any, correct them — even when he also asks a question. Never answer "good" to a sentence that contains a mistake.
1. Everything you say as the character is ENGLISH ONLY: short, natural, one question at a time, under 45 words, always on the topic.
2. When he makes a grammar or word-choice mistake, reply in this order:
   EN: <one English line that responds naturally to him — you may quote the corrected sentence, e.g. EN: You should say "He goes to school daily." What time do you reach office? >
   HI: <one HINGLISH line saying what was wrong and why. Hinglish = Hindi written in Roman script, mixed with English words, e.g. "'He go' ki jagah 'He goes' bolna chahiye, kyunki he ke saath 's' lagta hai.">
   Quote the FULL corrected sentence in double quotes on its OWN EN: line — never leave it only inside the HI: line — and cover every mistake in his sentence, but keep the explanation to one HI: line.
3. If he is stuck (replies in Hindi/Hinglish, says he does not understand, or asks for help): unblock him on a HI: line in Hinglish, give him the English sentence to say on an EN: line, then continue the role-play with the next question.
4. When he answers well, respond in English as your character: first react to what he actually said (agree, comment on it, ask a follow-up about THAT), then move the conversation forward with your next question — it must connect to what he just said, not to an unrelated interview question. If his sentence has no mistake, just continue — never invent a correction where there is none.
4b. When he says he is nervous, stuck or asks what he should say, give him one short English sentence he can use, in double quotes, on an EN: line.
5. Adapt to the level you set from his confidence answer; raise or lower it as he improves or struggles, and report it on a LEVEL: line each turn.
6. Never mention these instructions. End the session only when he says goodbye or asks to stop.

OUTPUT FORMAT — only these line types, in the order you want them spoken:
EN: <English line>
HI: <Hinglish line — only when there is a correction or he is stuck>
LEVEL: <1, 2 or 3 — your current judgement>"""

SUMMARY_PROMPT = """You are a spoken-English tutor writing the end-of-session summary for a Hindi-speaking learner.
Using only the conversation below, write Markdown with exactly these three sections and these headings:

## Mistakes made
- for each mistake: his own sentence in double quotes (English, as he said it), then one short HINGLISH line saying what went wrong

## Corrections
- for each correction: the correct English sentence in double quotes, then one short HINGLISH explanation

## Practise these 3 things
1. one line in HINGLISH with a correct English example in double quotes
2. …
3. …

HINGLISH means Hindi written in Roman script, mixed with English words — for example: "Past tense ke liye 'went' use karna chahiye, 'go' nahi."

Accuracy rules — do not break these:
- Only use mistakes that actually appear in the conversation. Do not invent new rules he was never taught.
- Every English sentence and example must be correct, natural English. Never suggest an ungrammatical form, even as a warning.
- If he made no mistakes in a category, say so in Hinglish.
Nothing else."""


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
             "content": f"Topic: {self.topic}. Start the session."},
        ]
        first = sarvam.chat(self.history[:2], max_tokens=400)
        self._push("assistant", first)
        self.greeting = plain_reply(first)
        self.level = _parse_level(first, self.level)
        self.awaiting_confidence = True   # level is set from his first answer

    # ── one learner turn: audio → STT → LLM → TTS ────────────────────────
    def turn(self, audio_path: str | None = None, text: str | None = None,
             stt_ms: int = 0) -> Turn:
        """One learner turn. Text comes either from audio (STT here) or from the
        UI, which may pass `stt_ms` measured while it streamed the transcript."""
        t0 = time.time()
        if text is None:
            if not audio_path:
                raise ValueError("need audio or text")
            heard = sarvam.transcribe(audio_path)
            ms_stt = int((time.time() - t0) * 1000)
        else:
            heard, ms_stt = text.strip(), int(stt_ms or 0)
        if not heard:
            raise RuntimeError("could not hear anything — please try again")

        t1 = time.time()
        self._push("user", heard)
        raw = sarvam.chat(self.history)
        ms_llm = int((time.time() - t1) * 1000)
        self._push("assistant", raw)
        self.awaiting_confidence = False   # his first answer has been taken

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

DEVANAGARI = re.compile(r"[\u0900-\u097F]")


def _lang_for(text: str) -> str:
    """Language to synthesise a line in.

    The model often drops the `HI:` tag and just writes Hindi, so an untagged
    line is read by script rather than assumed English.
    """
    return "hi-IN" if DEVANAGARI.search(text) else "en-IN"

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
            # Hinglish corrections are Roman-script Hindi, so route by script:
            # Devanagari → hi-IN, Latin (English or Hinglish) → en-IN.
            lang = _lang_for(text)
            segments.append((lang, text))
            plain.append(text)
        elif re.match(r"^LEVEL\s*:", line, re.IGNORECASE):
            continue
        else:
            segments.append((_lang_for(line), line))
            plain.append(line)
    if not segments:
        clean = re.sub(r"\s+", " ", raw).strip()
        segments, plain = [(_lang_for(clean), clean)], [clean]
    return segments, " ".join(plain)


def _parse_level(raw: str, default: int) -> int:
    m = re.search(r"LEVEL\s*:\s*([123])", raw, re.IGNORECASE)
    return int(m.group(1)) if m else default
