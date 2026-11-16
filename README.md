# Spoken English Tutor

A voice tutor that helps Hindi speakers learn spoken English. You talk to it —
it talks back — and it fixes your grammar on the spot with the explanation in
Hindi.

Built for the ZenBricks take-home assignment. **Only Sarvam AI models** are
used: Saaras v3 (speech-to-text), `sarvam-105b-conversations` (LLM),
Bulbul v3 (text-to-speech). No other model provider is involved.

## What it does

| # | Requirement | Where |
|---|---|---|
| 1 | Voice in, voice out (STT → LLM → TTS) | `tutor.Tutor.turn()` |
| 2 | Understands Hindi/Hinglish, explains in Hindi when stuck | `SYSTEM_PROMPT` rules 3–4 |
| 3 | Spoken conversation on a learner-picked topic | topic dropdown + session loop |
| 4 | Corrects grammar/word-choice with a short Hindi explanation | `EN:` / `HI:` reply format |
| 5 | Adapts difficulty to the learner's level | `LEVEL: 1/2/3` each turn, shown live in the UI |
| 6 | Ends with a written summary: mistakes, corrections, 3 practice items | **End session** button |
| 7 | Simple UI | Gradio (`app.py`) |

## Run it

```bash
git clone https://github.com/astromanish/spoken-english-tutor.git
cd spoken-english-tutor
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

export SARVAM_API_KEY=...        # https://dashboard.sarvam.ai → API keys
.venv/bin/python app.py          # → http://127.0.0.1:7860
```

Press **Start**, speak into the microphone (or type), and the tutor replies
aloud. **End session** writes the summary.

`ffmpeg` on your `PATH` converts whatever the browser records into the 16 kHz
WAV that Saaras expects; without it, uploaded WAVs still work.

## Why these models

- **Saaras v3 (STT)** — built for Indian languages and code-switching. A
  Hinglish sentence comes back as it was spoken instead of being mangled by an
  English-only transcriber. Free API tier.
- **sarvam-105b-conversations (LLM)** — the `-conversations` variant returns
  the answer in `content`; the base `sarvam-105b` is a reasoning model that
  hides it in `reasoning_content` and breaks standard chat clients. Handles the
  Hindi-explanation and English-reply mix in one call. Free API tier.
- **Bulbul v3 (TTS)** — Indian-English and Hindi voices that pronounce the
  names and code-switched words correctly. Free API tier.
- **Gradio** — native microphone input and audio playback components, so the
  whole voice UI is a few dozen lines.

## Design decisions

**One reply, two languages.** The model must speak English *and* explain in
Hindi in the same turn, so replies use a line format:

```
EN: You should say, "He goes to school daily." Do you understand?
HI: "He" के साथ "goes" लगता है, "go" नहीं।
LEVEL: 1
```

Each line is synthesised in its own language (`en-IN` / `hi-IN`) and the WAV
segments are concatenated into one continuous reply. Hindi explanations are
required in Devanagari, not romanised — it is clearer for the learner and
Bulbul reads the script correctly.

**Level is reported, not guessed by the UI.** The tutor judges the learner
after every turn and prints `LEVEL:`; the parser reads it back, so the badge in
the UI is the model's own assessment.

**Long recordings are chunked.** Saaras' REST endpoint caps files at 30 s, so
longer recordings are split with ffmpeg and the transcripts are joined.

**Summary comes from the transcript.** Ending the session replays the whole
conversation to the model with a fixed summarisation prompt — no state to drift.

**Transcripts are kept as spoken.** Saaras returns Hinglish in Devanagari
(`transcribe` mode), which is what the learner actually said; nothing is
silently translated.

## Evaluation

`python eval_run.py` runs **9 scripted learner utterances** through the real
voice pipeline (TTS → STT → tutor → TTS) and a judge model grades each reply
against the expectation for that utterance.

**9/9 handled correctly. Average response time 4.1 s**
(STT 0.9 s · LLM 0.5 s · TTS 2.8 s) on an Intel i7-9750H / 8 GB / Linux, with
all three models on Sarvam's cloud — the latency is network + model time, not
local compute.

| # | Learner said | Verdict | Time |
|---|---|---|---|
| 1 | Hello, main aaj office ja raha hoon. Kal ek meeting hai. | ✅ | 4.4s |
| 2 | He go to school daily. | ✅ | 3.9s |
| 3 | I am agree with you. | ✅ | 3.4s |
| 4 | Yesterday I go to office and I am explain everything to my manager. | ✅ | 4.4s |
| 5 | mujhe samajh nahi aaya, aap phir se bolo | ✅ | 4.2s |
| 6 | She don't know nothing about the job. | ✅ | 4.8s |
| 7 | Main bahut nervous hoon, interview mein kya bolun? | ✅ | 4.1s |
| 8 | I am working in company from two years. | ✅ | 5.0s |
| 9 | Last weekend I travelled to Jaipur with my cousins and we tried the local street food. | ✅ | 2.8s |

Full table, per-turn timings and judge notes: [`eval/results.md`](eval/results.md)
(raw: `eval/results.json`). Reproduce with `python eval_run.py`.

The cases cover Hinglish (1, 5, 7), subject–verb agreement (2, 6), "am + verb"
(3), past tense (4, 8), and a clean sentence where nothing should be corrected
(9).

## Layout

```
app.py         Gradio UI
tutor.py       session state, tutor prompt, turn handling, summary
sarvam.py      the three Sarvam API clients + audio helpers
eval_run.py    scripted evaluation → eval/results.{json,md}
```

## What I would improve next

- **Latency:** TTS dominates (~2.8 s). Streaming audio and starting synthesis
  while the LLM is still writing would cut the reply gap roughly in half.
- **True adaptation:** level changes are the model's judgement each turn; a
  spaced-repetition record of each mistake would make practice decisions
  durable instead of conversational.
- **Pronunciation feedback:** Saaras gives text, not phonetics — a scoring pass
  on the learner's actual audio would catch mispronounced words that are
  spelled correctly.
- **Offline mode:** everything runs on Sarvam's cloud today. A local Whisper +
  small Hindi-tuned TTS fallback would keep the tutor usable without a network.
