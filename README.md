# Spoken English Tutor

A live spoken-English tutor for Hindi speakers. Pick a scenario — job interview, doctor
visit, ordering food — and talk: the tutor plays the person in that conversation, corrects
your grammar the moment you make a mistake, explains *why* in Hinglish, and keeps going.
No typing, no push-to-talk, nothing to install.

Built as the ZenBricks take-home, using only Sarvam AI models: Saaras v3 (STT),
`sarvam-105b-conversations` (LLM), Bulbul v3 (TTS).

Python 3.12 · one process · browser Web Audio · `node --test` for turn-taking
Background and rationale for the internals: [`docs/architecture.md`](docs/architecture.md).
Rehearsal and demo material: [`docs/demo-rehearsal-job-interview.md`](docs/demo-rehearsal-job-interview.md),
[`docs/video-script-4min.md`](docs/video-script-4min.md).

---

## Setup

### What you need

| | |
|---|---|
| Python | **3.12** (3.11+ works; the steps below pin 3.12) |
| Sarvam API key | [dashboard.sarvam.ai](https://dashboard.sarvam.ai) — one key covers STT, chat and TTS |
| ffmpeg | optional. Used only for long-recording chunking and batch conversions; the browser uploads WAV, so the app runs without it |
| Node | optional, for the 17 JavaScript tests |
| Browser | Chrome, Edge or Safari, with microphone permission |

### Run it

```bash
git clone git@github.com:astromanish/spoken-english-tutor.git
cd spoken-english-tutor

# 1. dependencies
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. the key — never committed, never sent to the browser
printf 'SARVAM_API_KEY=your-key-here\n' > .env
chmod 600 .env
#    or, without leaving the key in shell history:
./scripts/set_key.sh

# 3. run
./run.sh                              # → http://127.0.0.1:7860
```

`run.sh` sources `.env` and starts `server.py`. Default port `7860`; when the host sets
`$PORT` the server binds `0.0.0.0:$PORT` instead.

Open the URL, allow the microphone, pick a scenario, press **Start**. The first line is
spoken to you — answer its confidence question (1–5) and the role-play begins. Talk
whenever you like; 750 ms of quiet hands the turn back. **End** writes the summary.

### Tests and measurements

```bash
node --test                                    # 17 turn-taking + WAV tests: no network, no mic
.venv/bin/python eval_run.py                   # 9 scripted learner utterances, judged → eval/
.venv/bin/python scripts/measure_latency.py 3  # live turn latency, against a running server
.venv/bin/python scripts/measure_vad.py        # re-calibrate the speech gate for a new mic/room
```

### Deploy

`render.yaml` is a working blueprint (Python runtime, `pip install -r requirements.txt`,
`python server.py`, health check `/api/meta`); set `SARVAM_API_KEY` in the dashboard, where
the blueprint marks it `sync: false` so it cannot land in git. `Dockerfile` is the same app
on `python:3.12-slim` with ffmpeg, for any container host:

```bash
docker build -t tutor . && docker run -p 7860:7860 -e SARVAM_API_KEY=… tutor
```

The app is one long-lived process — sessions in memory, one Sarvam websocket per
utterance — so it needs a host that keeps a process alive, not serverless functions.
Two things to know before pointing a public URL at it: the Render free plan sleeps after
~15 idle minutes (30–50 s cold start), and **there is no auth** — anyone with the link
spends your key. Keep it behind Tailscale or a password, or set a spend cap.

---

## Design decisions

**English is the conversation, Hinglish is the correction.** The tutor speaks only English
in character; the moment something is wrong — or the learner is stuck — it switches to
Hinglish (Hindi in Roman script, mixed with English words) for exactly that line, then
returns to English:

```
EN: You should say "He goes to school daily."
HI: 'He go' ki jagah 'He goes' bolna chahiye, kyunki he ke saath 's' lagta hai.
NEXT:
EN: What time do you reach office?
LEVEL: 1
```

**The correction is its own message.** A question wedged inside a correction is what the
learner remembers instead of the fix, so `NEXT:` splits the reply: message one is the
corrected sentence plus the Hinglish reason and nothing else, message two is the next
question. Both are synthesised in parallel and played back to back, so a turn costs the
slower of the two rather than the sum. A reply with nothing to correct carries no `NEXT:`.

**The transcript keeps the mistake.** `mode=codemix` transcribes what was actually said —
`"She don't know nothing"` stays a double negative. `transcribe` mode silently repaired
grammar in **2 of 6** test recordings, which would erase the thing being corrected, and
`verbatim` flips English into Devanagari, which the tutor cannot quote back.

**Routing is by script, not by tag.** Both `EN:` and Roman-script `HI:` lines go to the
`en-IN` voice, which reads code-mixed Indian English naturally; a line that arrives in
Devanagari goes to `hi-IN`. The model sometimes drops the tag, so script is the reliable
signal, and neighbouring lines in the same language are merged into one TTS request.

**Level comes from a confidence question, not a dropdown.** The first message asks the
learner to rate his English 1–5; the answer sets how hard the tutor corrects (1–2 → almost
everything, in short simple English; 3 → real mistakes plus better wording; 4–5 →
naturalness only). Words count as answers — "I am a beginner" is a self-description, not a
sentence to grammar-check — and the level is re-judged every turn on a `LEVEL:` line that
drives the badge.

**The ear is always open; 750 ms of quiet ends the turn.** Energy VAD in the browser
(128 ms blocks, gates calibrated from measured levels: speech ≈ 0.09 RMS, quiet room ≈
0.002), one transcription stream per utterance, and the next stream is opened before the
finished turn is awaited — so the tutor is never deaf while thinking or speaking. Talking
over it stops it mid-sentence; the gate doubles to 0.05 while its voice is playing, so only
real speech barges in. A learner who pauses mid-thought gets merged into one turn
(`replace_previous`) instead of being corrected twice.

**Speech streams; it is never waited for.** REST TTS returns nothing until the whole file
is rendered (2.2–3.3 s). `/speak/<token>` relays Bulbul's websocket as chunked
`linear16` PCM and the client schedules each chunk on the audio graph, so the first
syllable lands in ~0.4 s. PCM, not MP3: Web Audio schedules it with no codec at all,
barge-in is `source.stop()`, and it sidesteps browsers — and CI Chromium builds — that
ship without an MP3 decoder. The REST WAV path remains as a fallback.

**Turn-taking is DOM-free.** `static/vad.js` (the silence rule) and `static/turns.js`
(merge/hold/replace) contain no DOM, which is the only way to test the part of a voice UI
you cannot hear in CI. The rules, not the pixels, are what regress.

**One process, sessions keyed by cookie.** A voice agent is long-lived state, so it needs a
host that keeps a process alive. Each browser gets a `<app>_sid` cookie, the session map is
capped and evicts oldest, streams expire, and the API key never leaves the server.

**Nothing to install on the host.** The browser wraps its own PCM into a 44-byte RIFF
header (`static/wav.js`) instead of uploading `MediaRecorder` webm, so a host without
ffmpeg still accepts a recording.

**An empty session gets no summary.** With zero learner turns the model is not called —
asked to summarise a one-sided conversation it invents mistakes. That path returns a fixed,
honest blank state.

**Failures say one thing.** Every error path funnels through a single helper: the learner
sees *"Something went wrong. Start again."*, the real reason goes to the console. Error
codes are not copy.

---

## Evaluation results

Two separate questions, measured separately: **is the reply right** (`eval_run.py`, batch
path) and **how long does the learner wait** (`scripts/measure_latency.py`, the live path
the browser actually uses).

### Correctness — 9/9 scripted utterances

Each case is spoken with Bulbul, transcribed by Saaras, answered by the tutor, then graded
by a judge model against a written expectation. Full transcripts, prompts and per-case
notes: [`eval/results.md`](eval/results.md) (raw: `eval/results.json`).

| # | Learner said | What the tutor did | Verdict |
|---|---|---|---|
| 1 | Mujhe English bolne mein thoda confidence nahi hai, beginner level par hoon. | Acknowledged, set the level, started the interview | **PASS** |
| 2 | He go to school daily. | `"He goes to school daily."` + why third-person `-s` is needed | **PASS** |
| 3 | I am agree with you. | `"I agree with you."` + `agree` is already a verb | **PASS** |
| 4 | Yesterday I go to office and I am explain everything to my manager. | `"Yesterday I went to the office and I explained everything to my manager."` | **PASS** |
| 5 | mujhe samajh nahi aaya, aap phir se bolo | Unblocked in Hinglish, re-asked in simpler English | **PASS** |
| 6 | She don't know nothing about the job. | `"She does not know anything about the job."` + double negative explained | **PASS** |
| 7 | Main bahut nervous hoon, interview mein kya bolun? | Reassured in Hinglish, handed him a sentence to use | **PASS** |
| 8 | I am working in company from two years. | `"I have been working in a company for two years."` + present perfect | **PASS** |
| 9 | Last weekend I travelled to Jaipur with my cousins… | Nothing to correct: reacted to the story, kept the conversation going | **PASS** |

Models: STT `saaras:v3` (`codemix`) · chat `sarvam-105b-conversations` · TTS `bulbul:v3`.

**How honest this number is.** The judge is an LLM, and its first pass reported **6/9 on
replies that read as correct to a human** — it failed a reply containing an explicit
`"He goes to school daily."` quote while claiming the quote was missing, and it demanded a
"correction" for the nervous-learner case where no correction exists. Two real problems
were found and fixed rather than argued with:

- **Product:** a confidence answer given in words ("I am a beginner") was being corrected
  as grammar instead of read as the level. The tutor prompt now says so explicitly.
- **Judge:** the grading prompt now spells out what quoting and Hinglish look like,
  including single-clause Hinglish and quotes without a `You should say` prefix.

So 9/9 reflects current code **and** a clarified grader. Read it as "the behaviours below
are present in one run of 9 hand-written cases, in one scenario", not as an accuracy figure.

### Latency — the live path

Three consecutive turns through the same endpoints the page uses, with a 3.5 s learner
sentence (`scripts/measure_latency.py 3`):

| stage | what it measures | mean | spread |
|---|---|---|---|
| STT | turn closes → final transcript | **360 ms** | 350–373 |
| LLM | transcript → reply text + speech segments | **268 ms** | 241–284 |
| TTS | request → first PCM chunk out of `/speak` | **405 ms** | 387–425 |
| **first sound** | the three above | **1 034 ms** | 1 018–1 059 |

The 750 ms silence window is **not** in these numbers — it is the learner's own pause, not
cost. Add it for wall-clock from his last word: ≈1.8 s to first sound.

For comparison, the batch path `eval_run.py` uses (whole reply synthesised before it
returns) averages **4.5 s** per turn — STT 0.8 s + LLM 0.8 s + TTS 2.9 s. Streaming removes
the third number, which is why the UI never takes that path.

### What this evaluation does not cover

No automated check for: barge-in timing in real room noise, recognition accuracy on heavy
accents or quiet microphones, whether the Hinglish TTS sounds right to a native ear, or
long-session drift past 20 turns. Those were checked by hand on one machine (macOS, Apple
Silicon, all three models on Sarvam's cloud — the latency above is network + model time,
not local compute). They are the first things a reviewer should poke at.
