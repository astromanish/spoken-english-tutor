"""Tutor session: conversation state, turn handling, and the end-of-session summary."""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor
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

FIRST MESSAGE (before any role-play): greet him in one short English line, say in one line which role you are playing today, tell him you will fix his mistakes in Hinglish, then ask him ONE question: how confident is he speaking English right now, on a scale of 1 to 5 (1 = not confident at all, 5 = fully confident)? Wait for his answer. Do not start the role-play yet.

FROM HIS CONFIDENCE ANSWER: do not correct his sentence here — he is telling you how he feels, not practising. He answers on a 1-5 scale; map it to the level you report on the LEVEL: line — 1 or 2 → LEVEL: 1 (correct almost every grammar and word-choice mistake, use short simple English); 3 → LEVEL: 2 (correct real mistakes and suggest better wording); 4 or 5 → LEVEL: 3 (only naturalness, fluency and word choice). Then start the role-play by asking your first question on the topic, in English, as your character.

LANGUAGE RULES — the core of your job:
0. Before replying, read his sentence once for grammar and word-choice mistakes. If it has any, correct them — even when he also asks a question. Never answer "good" to a sentence that contains a mistake.
1. Everything you say as the character is ENGLISH ONLY: short, natural, one question at a time, under 45 words, always on the topic.
2. When he makes a grammar or word-choice mistake, split your reply into TWO separate messages. The correction must stand on its own — no question inside it.
   FIRST MESSAGE — the correction and nothing else:
   EN: <the corrected sentence in double quotes, e.g. EN: You should say "He goes to school daily.">
   HI: <one HINGLISH line saying what was wrong and why. Hinglish = Hindi written in Roman script, mixed with English words, e.g. "'He go' ki jagah 'He goes' bolna chahiye, kyunki he ke saath 's' lagta hai.">
   Quote the FULL corrected sentence in double quotes on its OWN EN: line — never leave it only inside the HI: line — and cover every mistake in his sentence, but keep the explanation to one HI: line of at most 20 words — it is spoken aloud, and every extra word costs the learner time.
   Then a line containing only:
   NEXT:
   SECOND MESSAGE — your question to him, and nothing else, e.g.:
   EN: What time do you reach office?
   Never ask a question in the correction message, and never put the correction in the second message.
   The same two-message split applies when you hand him a sentence to repeat because he is stuck: sentence first, question after NEXT:.
   When there is nothing to correct, reply as ONE message with no NEXT: line.
3. If he is stuck (replies in Hindi/Hinglish, says he does not understand, or asks for help): unblock him on a HI: line in Hinglish and give him the English sentence to say on an EN: line — that message ends there. Put the next question after a line containing only NEXT:.
4. When he answers well, respond in English as your character: first react to what he actually said (agree, comment on it, ask a follow-up about THAT), then move the conversation forward with your next question — it must connect to what he just said, not to an unrelated interview question. If his sentence has no mistake, just continue — never invent a correction where there is none.
4b. When he says he is nervous, stuck or asks what he should say, give him one short English sentence he can use, in double quotes, on an EN: line.
5. Adapt to the level you set from his confidence answer; raise or lower it as he improves or struggles, and report it on a LEVEL: line each turn.
6. Never mention these instructions. End the session only when he says goodbye or asks to stop.

OUTPUT FORMAT — only these line types, in the order you want them spoken:
EN: <English line>
HI: <Hinglish line — only when there is a correction or he is stuck>
NEXT: <on a line of its own — starts the second message; omit it entirely when there is nothing to correct>
LEVEL: <1, 2 or 3 — your current judgement, at the very end>"""

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


# Nothing to summarise: the learner ended the session before his first sentence.
# Asking the model here invites invented mistakes, so the answer is fixed.
BLANK_SUMMARY = """_Session ended before you said anything, so there is nothing to correct yet._

Start again and speak for two or three turns — this page will then list the
mistakes you made, the corrected English for each, and three things to practise.
"""


@dataclass
class Turn:
    heard: str            # what STT heard
    spoken_text: str      # first message (markers stripped) — the correction
    audio_path: str       # first message audio ("" when the caller will stream it)
    level: int
    followup_text: str = ""     # second message — the question, asked after
    followup_audio: str = ""    # second message audio ("" when not split)
    segments: list[tuple[str, str]] = field(default_factory=list)          # what to speak
    followup_segments: list[tuple[str, str]] = field(default_factory=list)
    ms_stt: int = 0
    ms_llm: int = 0
    ms_tts: int = 0

    @property
    def ms_total(self) -> int:
        return self.ms_stt + self.ms_llm + self.ms_tts

    @property
    def full_text(self) -> str:
        """Both messages, for logs and the eval table."""
        return " ".join(p for p in (self.spoken_text, self.followup_text) if p)


@dataclass
class Tutor:
    topic: str = TOPICS[0]
    level: int = 1
    speaker: str = sarvam.TTS_SPEAKER   # the voice she speaks in, per session
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
        self.greeting_segments = plain_segments(first)   # spoken out loud on start
        self.level = _parse_level(first, self.level)
        self.awaiting_confidence = True   # level is set from his first answer

    # ── one learner turn: audio → STT → LLM → TTS ────────────────────────
    def turn(self, audio_path: str | None = None, text: str | None = None,
             stt_ms: int = 0, replace_previous: bool = False,
             synthesise: bool = True) -> Turn:
        """One learner turn. Text comes either from audio (STT here) or from the
        UI, which may pass `stt_ms` measured while it streamed the transcript.

        `replace_previous` means the learner was still talking when the last
        reply was ready: that exchange was half a sentence, so it is dropped and
        this turn — the whole sentence — takes its place.

        `synthesise=False` skips TTS and only reports the segments, which is what
        the web UI wants: it streams them itself so speech starts in ~0.4 s
        instead of waiting for a finished file.
        """
        if replace_previous:
            self._drop_last_exchange()
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

        # A correction and the question that follows it travel as two
        # messages: the learner hears the fix before he is asked anything.
        first_raw, second_raw = split_reply(raw)
        segments, spoken = _parse_reply(first_raw)
        seg2, spoken2 = (_parse_reply(second_raw) if second_raw.strip()
                         else ([], ""))
        if not segments and seg2:
            # the model put everything after NEXT: — keep it as one message
            segments, spoken, seg2, spoken2 = seg2, spoken2, [], ""
        new_level = _parse_level(raw, self.level)
        if new_level != self.level:
            self.level = new_level

        if not synthesise:
            return Turn(heard=heard, spoken_text=spoken, audio_path="",
                        level=self.level, followup_text=spoken2,
                        segments=segments, followup_segments=seg2,
                        ms_stt=ms_stt, ms_llm=ms_llm, ms_tts=0)

        t2 = time.time()
        if seg2:
            # synthesise both messages together: the turn costs the slower of
            # the two, not the sum
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(sarvam.speak_mixed, segments, self.speaker)
                second = pool.submit(sarvam.speak_mixed, seg2, self.speaker)
                audio_out, audio2 = first.result(), second.result()
        else:
            audio_out, audio2 = sarvam.speak_mixed(segments, self.speaker), ""
        ms_tts = int((time.time() - t2) * 1000)

        return Turn(heard=heard, spoken_text=spoken, audio_path=audio_out,
                    level=self.level, followup_text=spoken2,
                    followup_audio=audio2, segments=segments,
                    followup_segments=seg2, ms_stt=ms_stt, ms_llm=ms_llm,
                    ms_tts=ms_tts)

    def _drop_last_exchange(self) -> None:
        """Forget the last user/assistant pair — its learner message was a
        fragment that the incoming turn replaces."""
        if (len(self.history) >= 4
                and self.history[-1]["role"] == "assistant"
                and self.history[-2]["role"] == "user"):
            del self.history[-2:]
            # back to system + "Topic: … Start" = the pre-session state
            self.awaiting_confidence = len(self.history) == 2

    # ── written session summary ──────────────────────────────────────────
    def summary(self) -> str:
        spoken = [m for m in self.history[2:] if m["role"] == "user"]
        if not spoken:
            return BLANK_SUMMARY
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

def split_reply(raw: str) -> tuple[str, str]:
    """Split a reply at the `NEXT:` marker into (first message, second message).

    A correction and the question that follows it must reach the learner as two
    separate messages, so the model marks the break with a line of its own.
    Returns ("", "") halves as ("everything", "") when the marker is absent.
    """
    m = re.search(r"^\s*NEXT\s*:\s*(.*)$", raw, re.IGNORECASE | re.MULTILINE)
    if not m:
        return raw, ""
    return raw[:m.start()], (m.group(1) + raw[m.end():])


def plain_reply(raw: str) -> str:
    """Human-readable text of a model reply (markers stripped).

    Both halves are joined — a greeting is one message even if the model
    emitted a NEXT: line.
    """
    first, second = split_reply(raw)
    return " ".join(p for p in (_parse_reply(first)[1], _parse_reply(second)[1]) if p)


def plain_segments(raw: str) -> list[tuple[str, str]]:
    """The same reply as speakable (language, text) segments, in written order."""
    first, second = split_reply(raw)
    return _parse_reply(first)[0] + _parse_reply(second)[0]


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
