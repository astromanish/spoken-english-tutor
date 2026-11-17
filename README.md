1|# Priyanka ( Spoken English Tutor )
2|
3|A voice tutor that helps Hindi speakers learn spoken English by **role-playing**
4|a real conversation. You pick a topic and the tutor plays the person in it — the
5|interviewer, the waiter, the doctor — holds the whole conversation in **English**,
6|and asks you questions on that topic. The moment you make a grammar or
7|word-choice mistake it corrects you in **Hinglish**, so you always understand
8|why: *"'He go' ki jagah 'He goes' bolna chahiye, kyunki he ke saath 's' lagta
9|hai."*
10|
11|Built for the ZenBricks take-home assignment, for Priyanka. **Only Sarvam AI models** are
12|used: Saaras v3 (speech-to-text), `sarvam-105b-conversations` (LLM),
13|Bulbul v3 (text-to-speech). No other model provider is involved.
14|
15|## What it does
16|
17|| # | Requirement | Where |
18||---|---|---|
19|| 1 | Voice in, voice out (STT → LLM → TTS) | `tutor.Tutor.turn()` |
20|| 2 | Understands Hindi and Hinglish; helps when the learner is stuck | stuck-learner rule in `SYSTEM_PROMPT`, answered in Hinglish |
21|| 3 | Role-played conversation on a learner-picked topic | persona per topic (interviewer, waiter, doctor…) + session loop |
22|| 4 | Corrects grammar/word-choice, explanation in Hinglish | English reply on `EN:`, Hinglish explanation on `HI:` |
23|| 5 | Adapts difficulty to the learner's level | confidence question in the first message sets `LEVEL`, re-judged every turn |
24|| 6 | Ends with a written summary: mistakes, corrections, 3 practice items | **End session** button |
25|| 7 | Simple UI | vanilla JS (`static/`) on a stdlib server (`server.py`) |
26|| + | Live transcript while you speak | `realtime.py`, the live panel above the mic |
27|
28|## Run it
29|
30|```bash
31|git clone https://github.com/astromanish/spoken-english-tutor.git
32|cd spoken-english-tutor
33|python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
34|
35|export SARVAM_API_KEY=...        # https://dashboard.sarvam.ai → API keys
36|.venv/bin/python server.py       # → http://127.0.0.1:7860
37|```
38|
39|Press **Start** and the tutor introduces its character, then asks how confident
40|you are speaking English — that answer sets how much it corrects you. Tap the
41|mic and speak (or type); the tutor replies aloud and keeps the conversation
42|going. **End session** writes the summary.
43|
44|While the mic is open, a live transcript of what Saaras hears appears above it;
45|press the mic again and that transcript becomes your turn.
46|
47|`ffmpeg` on your `PATH` converts the fallback recording (a browser upload posted
48|to `/api/turn`) into the 16 kHz WAV that Saaras expects; without it, WAV uploads
49|still work and the streaming path is unaffected.
50|
51|## Why these models
52|
53|- **Saaras v3 (STT)** — built for Indian languages and code-switching. A
54|  Hinglish sentence comes back as it was spoken instead of being mangled by an
55|  English-only transcriber. The live transcript uses `saaras:v3-realtime`, the
56|  same model over a websocket, so the words on screen are the words the turn
57|  runs on. Free API tier.
58|- **sarvam-105b-conversations (LLM)** — the `-conversations` variant returns
59|  the answer in `content`; the base `sarvam-105b` is a reasoning model that
60|  hides it in `reasoning_content` and breaks standard chat clients. Handles the
61|  English-conversation and Hinglish-correction mix in one call, and holds the
62|  role-play persona turn after turn. Free API tier.
63|- **Bulbul v3 (TTS)** — Indian-English and Hindi voices that pronounce the
64|  names and code-switched words correctly. Free API tier.
65|- **No UI framework** — the browser captures with Web Audio, plays the reply
66|  through an `<audio>` element, and talks to a handful of JSON endpoints
67|  (`/api/meta`, `/api/session`, `/api/turn`, `/api/summary`, `/api/stream/*`).
68|  `server.py` is `http.server` from the standard library, so the app's only
69|  dependencies are `requests`, `pyyaml` and `websockets`. Gradio was dropped
70|  because it pinned a large dependency tree for a UI that is one page of HTML.
71|
72|## Design decisions
73|
74|**English is the conversation, Hinglish is the correction.** The tutor plays a
75|character and speaks only English; the moment something is wrong — or the
76|learner is stuck — it switches to Hinglish (Hindi in Roman script, mixed with
77|English words) for that one line, then goes back to English:
78|
79|```
80|EN: You should say "He goes to school daily." What time do you reach office?
81|HI: 'He go' ki jagah 'He goes' bolna chahiye, kyunki he ke saath 's' lagta hai.
82|LEVEL: 1
83|```
84|
85|Lines are spoken in the order written. Both are Latin script, so both go to the
86|`en-IN` Bulbul voice, which reads code-mixed Indian English naturally; a line
87|that arrives in Devanagari is routed to `hi-IN` instead. Routing is by script,
88|not by the `EN:`/`HI:` tag, because the model sometimes drops the tag — and
89|neighbouring lines in the same language are merged into one TTS request.
90|
91|**Segments are synthesised in parallel.** Each language segment is its own TTS
92|request; they run concurrently and are stitched back in the written order, so an
93|English+Hinglish reply costs about its slowest segment instead of the sum, and one
94|slow call is retried rather than stalling the turn.
95|
96|**Level starts with a confidence question, not a dropdown.** The setup has no
97|level picker: the first message asks how confident he is speaking English, his
98|answer sets how hard the tutor comes down on grammar and word choice (1 = almost
99|every mistake, 2 = real mistakes plus better wording, 3 = fluency only), and the
100|tutor re-judges it every turn — reported on a `LEVEL:` line the parser reads
101|back for the badge.
102|
103|**The live transcript is the turn.** While the mic is open the page sends
104|250 ms of 16 kHz PCM to `POST /api/stream/<id>/audio`; `realtime.py` holds one
105|websocket to `saaras:v3-realtime` per recording and returns whatever
106|`transcript.partial` events have arrived, so the panel updates as the learner
107|speaks. The key stays on the server — the browser never opens a websocket of
108|its own, and no second port is needed. When the learner stops, a short silence
109|tail flushes the VAD and the `transcript.final` text is what the turn runs on,
110|so the words on screen are exactly the words the tutor corrects. A
111|`MediaRecorder` runs alongside as a fallback: if the stream yields nothing the
112|recording is uploaded and transcribed the old way.
113|
114|**Long recordings are chunked.** Saaras' REST endpoint caps files at 30 s, so
115|longer uploaded recordings are split with ffmpeg and the transcripts joined by
116|the stream instead.
117|
118|**Summary comes from the transcript.** Ending the session replays the whole
119|conversation to the model with a fixed summarisation prompt — no state to drift.
120|
121|**Transcripts are kept as spoken.** Saaras returns Hinglish in Devanagari
122|(`transcribe` mode), which is what the learner actually said; nothing is
123|silently translated.
124|
125|## Evaluation

`python eval_run.py` runs **9 scripted learner utterances** through the real
voice pipeline (TTS → STT → tutor → TTS) and a judge model grades each reply
against the expectation for that utterance.

**7/9 handled correctly. Average response time 6.2 s**
(STT 2.2 s · LLM 1.3 s · TTS 2.7 s) on an Intel i7-9750H / 8 GB / Linux, with
all three models on Sarvam's cloud — the latency is network + model time, not
local compute. A reply is an English line plus a Hinglish correction line, so
it is synthesised as two or three segments; those run in parallel and are
stitched in order, which is why TTS stays near a single call.

| # | Learner said | Verdict | Time |
|---|---|---|---|
| 1 | Mujhe English bolne mein thoda confidence nahi hai, beginner level par hoon. | ✅ | 3.9s |
| 2 | He go to school daily. | ❌ | 4.1s |
| 3 | I am agree with you. | ✅ | 23.5s |
| 4 | Yesterday I go to office and I am explain everything to my manager. | ✅ | 5.2s |
| 5 | mujhe samajh nahi aaya, aap phir se bolo | ✅ | 3.6s |
| 6 | She don't know nothing about the job. | ✅ | 3.5s |
| 7 | Main bahut nervous hoon, interview mein kya bolun? | ✅ | 3.8s |
| 8 | I am working in company from two years. | ✅ | 3.5s |
| 9 | Last weekend I travelled to Jaipur with my cousins and we tried the local street food. | ❌ | 5.2s |

Full table, per-turn timings and judge notes: [`eval/results.md`](eval/results.md)
(raw: `eval/results.json`). Reproduce with `python eval_run.py`.

The cases cover the confidence answer that sets the level (1), subject–verb
agreement (2, 6), "am + verb" (3), past tense (4, 8), a learner stuck in
Hinglish (5), a nervous learner who needs a sentence to say (7), and a clean
sentence where nothing should be corrected (9).

The score moves a point or two between runs — tutor and judge both sample — so
the table is the last run, not a cherry-picked one. Two failure modes surfaced
while testing: Saaras rejecting a TTS file it could not read (HTTP 400; fixed by
re-encoding every reply to 16 kHz mono before transcribing) and the tutor
occasionally leaving the corrected sentence inside the Hinglish line instead of
putting it on its own `EN:` line.

## Layout
158|
159|```
160|server.py      HTTP server + JSON API (stdlib, no framework)
161|realtime.py    live transcription: PCM in over HTTP, one websocket to Saaras
162|static/        index.html, style.css, app.js — the whole UI
163|tutor.py       session state, tutor prompt, turn handling, summary
164|sarvam.py      the three Sarvam API clients + audio helpers
165|eval_run.py    scripted evaluation → eval/results.{json,md}
166|```
167|
168|## What I would improve next
169|
170|- **Latency:** TTS still dominates (~1.8 s even with parallel segments).
171|  Streaming the reply audio so playback starts on the first sentence, instead
172|  of waiting for the whole WAV, would cut the perceived gap again — the input
173|  side already streams.
174|- **True adaptation:** the level starts from his own confidence answer and the
175|  model re-judges it every turn, so the same mistake can be corrected hard early
176|  and left alone later; a spaced-repetition record of each mistake would make
177|  practice decisions durable instead of conversational.
178|- **Pronunciation feedback:** Saaras gives text, not phonetics — a scoring pass
179|  on the learner's actual audio would catch mispronounced words that are
180|  spelled correctly.
181|- **Offline mode:** everything runs on Sarvam's cloud today. A local Whisper +
182|  small Hindi-tuned TTS fallback would keep the tutor usable without a network.