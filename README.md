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
| + | A live voice agent, not a chat box | ears and mouth always on: `static/app.js` + `static/vad.js` |
| + | Five voices to choose from, with a preview | Voice select + `POST /api/preview` |
| + | Turn ends after **0.75 s** of silence; one icon mutes the mic | `TurnWatcher` in `static/vad.js`, tested in `tests/` |

## Run it

```bash
git clone https://github.com/astromanish/spoken-english-tutor.git
cd spoken-english-tutor
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

export SARVAM_API_KEY=...        # https://dashboard.sarvam.ai → API keys
.venv/bin/python server.py       # → http://127.0.0.1:7860
```

Press **Start** and her ear opens while her first line plays out loud: she
introduces her character and asks how confident you are speaking English, on a
scale of 1 to 5 — that answer sets how much she corrects you. Then just talk. She answers out loud,
asks the next thing, and keeps going; **End** writes the summary.

The **Voice** picker offers five of bulbul:v3's 37 speakers, described by
character rather than by name — *Warm female · Calm female · Young female ·
Professional male · Mature male* — because the tutor is Priyanka either way; the
choice is how she sounds, not who she is. **Preview** speaks a two-line sample in
that voice (one English line, one Hinglish line, so you hear both before
committing) — and the sample introduces itself as **Priyanka** for the female
voices and **Priyank** for the male ones. The pick is remembered in `localStorage` and travels with the
session as a `speaker` field; an unknown or retired one falls back to the default
rather than failing the start.

There is no text box and no transcript log. The ear stays open the whole
session, including while she is speaking — if you talk over her she stops
mid-sentence and takes what you said instead. The round **mic button** closes the
microphone for real — the track is stopped, so the OS indicator goes out — and
shows a crossed mic while it is closed.

`ffmpeg` on your `PATH` converts the fallback recording (a browser upload posted
to `/api/turn`) into the 16 kHz WAV that Saaras expects; without it, WAV uploads
still work and the streaming path is unaffected.

## The live loop

Everything the browser does each ~256 ms block of microphone audio:

- **Level** → an RMS, which drives the orb and the turn-taking.
- **Speech** → the PCM goes to `POST /api/stream/<id>/audio`, so Saaras' live
  transcript fills the *You* line as you speak.
- **Silence** → after **0.75 s** with nothing above the gate (and at least 350 ms
  of speech in the utterance, so a cough is not a turn) the stream is stopped,
  the final transcript becomes your turn, and the next stream opens immediately
  so the ear is never shut while she thinks or speaks.
- **Barge-in** → talking while she is speaking is detected at a higher gate
  (0.05 RMS, versus 0.018 when she is quiet) and cuts her playback instead of
  waiting for her to finish; the ear stays open and the UI stays on *hearing*
  until he stops.
- **Half a second is a short leash**, so the continuation rule below earns its
  keep: a learner who pauses to think mid-sentence gets cut off, keeps talking,
  and her held answer is folded into the whole sentence instead of a fragment.
- **A pause mid-sentence does not split the turn** → if he starts talking again
  while she is still *thinking* (before any of her answer has been heard), that
  answer is held, not spoken over him, and his fragment is carried into the next
  turn — which goes out as one sentence with `replace_previous: true`, so the
  server drops the half-sentence from her history instead of correcting it
  twice. If the "continuation" turns out to be a cough, the held answer is
  played after all: no turn is ever lost.

The rule lives in `static/vad.js` as a DOM-free `TurnWatcher`, so it can be
tested without a microphone:

```bash
node --test                # 17 tests: the 0.75 s edge, coughs, room noise, echo,
                           #            barge-in vs continuation merge, held replies
```

Thresholds were measured, not guessed: Bulbul speech sits around 0.09 RMS, a
quiet room near 0.002, and digital silence at 0.0 — a 40× margin under the
gate. `echoCancellation`, `noiseSuppression` and `autoGainControl` are all on
for the mic, which is what keeps her own voice out of the turn-taking.

## Latency

Measured against the live API from this machine (`bulbul:v3`, en-IN, one speaker):

| text | characters | new connection | pooled | audio | bytes @22 k |
|---|---|---|---|---|---|
| "What time do you reach office?" | 30 | 0.81 s | 0.70 s | 2.6 s | 87 KB |
| corrected sentence + Hinglish line | 110 | 2.46 s | 1.86 s | 5.4 s | 290 KB |
| two-clause correction | 240 | 4.29 s | 3.35 s | 15.0 s | 527 KB |

Synthesis is roughly **linear in characters** (≈14–23 s per 1 000 characters), so
the cost is the explanation, not the network. Four things follow:

- **Pooled connections.** A fresh TLS handshake per call cost 0.15–0.95 s, and a
  turn makes two calls → `requests.Session` with an HTTPAdapter.
- **16 kHz instead of Bulbul's 22.05 kHz default** via `speech_sample_rate`:
  376 KB instead of 592 KB for the same sentence, and 0.5 s quicker. The browser
  does not need the extra bandwidth.
- **Cap the spoken explanation** at 20 words in the prompt: the Hinglish
  correction is the longest thing she says, and every word is synthesis time.
- **ffmpeg is not the problem** — re-encoding a 15 s reply takes 0.07 s. It stays
  because STT needs a deterministic format, not for speed.

Together that moved a turn from 3.4–6.6 s to a median **2.6 s (llm 0.35 s, tts
2.2 s)**. The remaining win is streaming: Bulbul can emit audio over a websocket,
and playing the first sentence while the second is still being synthesised
removes most of the wait the learner actually feels.

## Deploying

The app is one long-lived Python process: sessions in memory, one Sarvam
websocket per recording, audio kept in a dict. That is a *server*, and it rules
out pure serverless hosts.

**Render — free, no Docker.** Push the repo, then *New → Blueprint* and pick this
repository: `render.yaml` builds `pip install -r requirements.txt` and starts
`python server.py`. Add `SARVAM_API_KEY` in the dashboard when it asks. The free
plan sleeps after ~15 idle minutes, so the first visitor waits ~30 s for a cold
start.

**Any container host** (Fly, Railway, Cloud Run, a VPS):
`docker build -t priyanka . && docker run -p 7860:7860 -e SARVAM_API_KEY=… priyanka`.
The `Dockerfile` installs ffmpeg, which the audio normalisation needs.

**Netlify cannot run this app.** The only Netlify primitive that fits is
[Netlify Server](https://docs.netlify.com/build/server/) — long-lived, holds
websockets, keeps state — and it refuses a Free plan with
`422 Netlify Server is only available on credit-based plans`. Netlify Functions
are JS/TS only, cannot hold the Sarvam websocket across a request, and have no
ffmpeg, so a Netlify build would need a JS rewrite *and* would lose the live
transcript.

Sessions are per browser (a `priyanka_sid` cookie), so a shared URL gives each
visitor their own tutor. There is no auth: anyone with the link spends the Sarvam
key's free tier, so keep the URL to people you know.

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
  (`/api/meta`, `/api/session`, `/api/turn`, `/api/summary`, `/api/preview`,
  `/api/stream/*`).
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
level picker: the first message asks him to rate his English confidence **1 to 5**
(1 = not confident at all, 5 = fully confident). That answer maps onto how hard
the tutor comes down on him — 1–2 → almost every mistake in short simple English,
3 → real mistakes plus better wording, 4–5 → naturalness and word choice only —
and the tutor re-judges it every turn, reported on a `LEVEL:` line the parser
reads back for the badge.

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
With **zero learner turns** the model is not called at all: there is nothing to
correct, and a model asked to summarise a one-sided conversation invents
mistakes. That case returns a fixed, honest blank state instead.

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
static/        index.html, style.css, app.js — the whole voice UI
static/vad.js  turn-taking: silence → turn, barge-in — DOM-free, node-tested
static/turns.js continuation + barge-in bookkeeping (merge, hold, replace)
tests/         `node --test` — the silence rule and its edge cases
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