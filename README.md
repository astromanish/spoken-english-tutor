# Priyanka ( Spoken English Tutor )

A voice tutor that helps Hindi speakers learn spoken English by **role-playing**
a real conversation. You pick a topic and the tutor plays the person in it — the
interviewer, the waiter, the doctor — holds the whole conversation in **English**,
and asks you questions on that topic. The moment you make a grammar or
word-choice mistake it corrects you in **Hinglish**, so you always understand
why: *"'He go' ki jagah 'He goes' bolna chahiye, kyunki he ke saath 's' lagta
hai."*

Built for the ZenBricks take-home assignment, for Priyanka. **Only Sarvam AI models** are
used: Saaras v3 (speech-to-text), `sarvam-105b-conversations` (LLM),
Bulbul v3 (text-to-speech). No other model provider is involved.

## What it does

| # | Requirement | Where |
|---|---|---|
| 1 | Voice in, voice out (STT → LLM → TTS) | `tutor.Tutor.turn()` |
| 2 | Understands Hindi and Hinglish; helps when the learner is stuck | stuck-learner rule in `SYSTEM_PROMPT`, answered in Hinglish |
| 3 | Role-played conversation on a learner-picked topic | persona per topic (interviewer, waiter, doctor…) + session loop |
| 4 | Corrects grammar/word-choice, explanation in Hinglish | English reply on `EN:`, Hinglish explanation on `HI:` |
| 5 | Adapts difficulty to the learner's level | confidence question in the first message sets `LEVEL`, re-judged every turn |
| 6 | Ends with a written summary: mistakes, corrections, 3 practice items | **End session** button |
| 7 | Simple UI | vanilla JS (`static/`) on a stdlib server (`server.py`) |
| + | Live transcript while you speak | `realtime.py`, the live panel above the mic |

## Run it

```bash
git clone https://github.com/astromanish/spoken-english-tutor.git
cd spoken-english-tutor
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

export SARVAM_API_KEY=...        # https://dashboard.sarvam.ai → API keys
.venv/bin/python server.py       # → http://127.0.0.1:7860
```

Press **Start** and the tutor introduces its character, then asks how confident
you are speaking English — that answer sets how much it corrects you. Tap the
mic and speak (or type); the tutor replies aloud and keeps the conversation
going. **End session** writes the summary.

While the mic is open, a live transcript of what Saaras hears appears above it;
press the mic again and that transcript becomes your turn.

`ffmpeg` on your `PATH` converts the fallback recording (a browser upload posted
to `/api/turn`) into the 16 kHz WAV that Saaras expects; without it, WAV uploads
still work and the streaming path is unaffected.

## Why these models

- **Saaras v3 (STT)** — built for Indian languages and code-switching. A
  Hinglish sentence comes back as it was spoken instead of being mangled by an
  English-only transcriber. The live transcript uses `saaras:v3-realtime`, the
  same model over a websocket, so the words on screen are the words the turn
  runs on. Free API tier.
- **sarvam-105b-conversations (LLM)** — the `-conversations` variant returns
  the answer in `content`; the base `sarvam-105b` is a reasoning model that
  hides it in `reasoning_content` and breaks standard chat clients. Handles the
  English-conversation and Hinglish-correction mix in one call, and holds the
  role-play persona turn after turn. Free API tier.
- **Bulbul v3 (TTS)** — Indian-English and Hindi voices that pronounce the
  names and code-switched words correctly. Free API tier.
- **No UI framework** — the browser captures with Web Audio, plays the reply
  through an `<audio>` element, and talks to a handful of JSON endpoints
  (`/api/meta`, `/api/session`, `/api/turn`, `/api/summary`, `/api/stream/*`).
  `server.py` is `http.server` from the standard library, so the app's only
  dependencies are `requests`, `pyyaml` and `websockets`. Gradio was dropped
  because it pinned a large dependency tree for a UI that is one page of HTML.

## Design decisions

**English is the conversation, Hinglish is the correction.** The tutor plays a
character and speaks only English; the moment something is wrong — or the
learner is stuck — it switches to Hinglish (Hindi in Roman script, mixed with
English words) for that one line, then goes back to English:

```
EN: You should say "He goes to school daily."
HI: 'He go' ki jagah 'He goes' bolna chahiye, kyunki he ke saath 's' lagta hai.
NEXT:
EN: What time do you reach office?
LEVEL: 1
```

**The correction is its own message.** A question wedged into the middle of a
correction is what the learner remembers instead of the fix, so `NEXT:` splits
the reply in two: message one is the corrected sentence plus the Hinglish reason
and nothing else, message two is the next question. The UI shows them as two
bubbles and plays them back to back, and both are synthesised in parallel so the
turn still costs the slower of the two rather than the sum. Replies with nothing
to correct carry no `NEXT:` and stay a single message.

Lines are spoken in the order written. Both are Latin script, so both go to the
`en-IN` Bulbul voice, which reads code-mixed Indian English naturally; a line
that arrives in Devanagari is routed to `hi-IN` instead. Routing is by script,
not by the `EN:`/`HI:` tag, because the model sometimes drops the tag — and
neighbouring lines in the same language are merged into one TTS request.

**Segments are synthesised in parallel.** Each language segment is its own TTS
request; they run concurrently and are stitched back in the written order, so an
English+Hinglish reply costs about its slowest segment instead of the sum, and one
slow call is retried rather than stalling the turn.

**Level starts with a confidence question, not a dropdown.** The setup has no
level picker: the first message asks how confident he is speaking English, his
answer sets how hard the tutor comes down on grammar and word choice (1 = almost
every mistake, 2 = real mistakes plus better wording, 3 = fluency only), and the
tutor re-judges it every turn — reported on a `LEVEL:` line the parser reads
back for the badge.

**The live transcript is the turn.** While the mic is open the page sends
250 ms of 16 kHz PCM to `POST /api/stream/<id>/audio`; `realtime.py` holds one
websocket to `saaras:v3-realtime` per recording and returns whatever
`transcript.partial` events have arrived, so the panel updates as the learner
speaks. The key stays on the server — the browser never opens a websocket of
its own, and no second port is needed. When the learner stops, a short silence
tail flushes the VAD and the `transcript.final` text is what the turn runs on,
so the words on screen are exactly the words the tutor corrects. A
`MediaRecorder` runs alongside as a fallback: if the stream yields nothing the
recording is uploaded and transcribed the old way.

**Long recordings are chunked.** Saaras' REST endpoint caps files at 30 s, so
longer uploaded recordings are split with ffmpeg and the transcripts joined by
the stream instead.

**Summary comes from the transcript.** Ending the session replays the whole
conversation to the model with a fixed summarisation prompt — no state to drift.

**Transcripts are kept as spoken.** Saaras returns Hinglish in Devanagari
(`transcribe` mode), which is what the learner actually said; nothing is
silently translated.

## Evaluation

`python eval_run.py` runs **9 scripted learner utterances** through the real
voice pipeline (TTS → STT → tutor → TTS) and a judge model grades each reply
against the expectation for that utterance.

**7/9 handled correctly. Average response time 4.1 s**
(STT 0.9 s · LLM 0.5 s · TTS 2.7 s) on an Intel i7-9750H / 8 GB / Linux, with
all three models on Sarvam's cloud — the latency is network + model time, not
local compute. A reply is one or two messages of an English line plus a
Hinglish correction line; the segments run in parallel and are stitched in
order, which is why TTS stays near a single call.

| # | Learner said | Verdict | Time |
|---|---|---|---|
| 1 | Mujhe English bolne mein thoda confidence nahi hai, beginner level par hoon. | ✅ | 3.1s |
| 2 | He go to school daily. | ✅ | 4.1s |
| 3 | I am agree with you. | ✅ | 4.7s |
| 4 | Yesterday I go to office and I am explain everything to my manager. | ✅ | 5.5s |
| 5 | mujhe samajh nahi aaya, aap phir se bolo | ✅ | 3.2s |
| 6 | She don't know nothing about the job. | ✅ | 4.9s |
| 7 | Main bahut nervous hoon, interview mein kya bolun? | ❌ | 3.4s |
| 8 | I am working in company from two years. | ✅ | 4.7s |
| 9 | Last weekend I travelled to Jaipur with my cousins and we tried the local street food. | ❌ | 3.0s |

Full table, per-turn timings and judge notes: [`eval/results.md`](eval/results.md)
(raw: `eval/results.json`). Reproduce with `python eval_run.py`.

The cases cover the confidence answer that sets the level (1), subject–verb
agreement (2, 6), "am + verb" (3), past tense (4, 8), a learner stuck in
Hinglish (5), a nervous learner who needs a sentence to say (7), and a clean
sentence where nothing should be corrected (9).

Scores move a point between runs — tutor and judge both sample — so recent runs
land at 7–8 of 9. The misses are wording slips (a quote left unclosed, a
question that drifted off the learner's topic), never a broken turn: no run has
lost a reply or a transcript since the audio path was fixed.

## Speech-to-text: why `mode=codemix`

The transcript has to keep the learner's mistakes — a tutor that is handed
"He goes" can never correct "He go". Measured over 6 fresh recordings of one
deliberately ungrammatical sentence:

| mode | grammar silently fixed | script |
|---|---|---|
| `transcribe` (what this shipped with) | **2/6** — returned "He goes … I went … I am explaining" | Latin |
| `codemix` (now used) | **0/6** | Latin |
| `verbatim` | 0/6 | **Devanagari** — ही गो टू स्कूल, unusable here |
| `translate` | always | translates to English |

Both the batch endpoint and the live websocket (`realtime.py`) now read the
same `sarvam.STT_MODE`, so the two paths cannot drift apart again. Live-path
checks over HTTP: transcript returned and marked final, grammar preserved,
silence answered in 1.6 s instead of 6 s, and the webm fallback keeping the
mistakes — 10/10 in `e2e` testing.

## Layout

```
server.py      HTTP server + JSON API (stdlib, no framework)
realtime.py    live transcription: PCM in over HTTP, one websocket to Saaras
static/        index.html, style.css, app.js — the whole UI
tutor.py       session state, tutor prompt, turn handling, summary
sarvam.py      the three Sarvam API clients + audio helpers
eval_run.py    scripted evaluation → eval/results.{json,md}
```

## What I would improve next

- **Latency:** TTS still dominates (~1.8 s even with parallel segments).
  Streaming the reply audio so playback starts on the first sentence, instead
  of waiting for the whole WAV, would cut the perceived gap again — the input
  side already streams.
- **True adaptation:** the level starts from his own confidence answer and the
  model re-judges it every turn, so the same mistake can be corrected hard early
  and left alone later; a spaced-repetition record of each mistake would make
  practice decisions durable instead of conversational.
- **Pronunciation feedback:** Saaras gives text, not phonetics — a scoring pass
  on the learner's actual audio would catch mispronounced words that are
  spelled correctly.
- **Offline mode:** everything runs on Sarvam's cloud today. A local Whisper +
  small Hindi-tuned TTS fallback would keep the tutor usable without a network.