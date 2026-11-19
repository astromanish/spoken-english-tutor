# How it works — the long version

Background that used to live in the README: the live loop, the latency story,
the host and model choices, why `codemix`, deployment notes, and what is next.

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

## The live loop

Everything the browser does each 128 ms block of microphone audio:

- **Level** → an RMS, which drives the orb and the turn-taking.
- **Speech** → the PCM goes to `POST /api/stream/<id>/audio`, so Saaras' live
  transcript fills the *You* line as you speak.
- **Silence** → after **0.75 s** with nothing above the gate (and at least 350 ms
  of speech in the utterance, so a cough is not a turn) the stream is stopped,
  the final transcript becomes your turn, and the next stream opens immediately
  so the ear is never shut while the tutor thinks or speaks.
- **Barge-in** → talking while the tutor is speaking is detected at a higher gate
  (0.05 RMS, versus 0.018 when it is quiet) and cuts her playback instead of
  waiting for her to finish; the ear stays open and the UI stays on *hearing*
  until he stops.
- **Three quarters of a second is a short leash**, so the continuation rule below earns its
  keep: a learner who pauses to think mid-sentence gets cut off, keeps talking,
  and her held answer is folded into the whole sentence instead of a fragment.
- **A pause mid-sentence does not split the turn** → if he starts talking again
  while the tutor is still *thinking* (before any of the answer has been heard), that
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

> Historical: these are the pre-streaming REST measurements. Current numbers are in the
> README's *Evaluation results* section; the reasoning here is why streaming was worth it.

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
  correction is the longest thing spoken, and every word is synthesis time.
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
`docker build -t tutor . && docker run -p 7860:7860 -e SARVAM_API_KEY=… tutor`.
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
