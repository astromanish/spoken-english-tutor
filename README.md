1|1|# Priyanka ( Spoken English Tutor )
2|2|
3|3|A voice tutor that helps Hindi speakers learn spoken English by **role-playing**
4|4|a real conversation. You pick a topic and the tutor plays the person in it — the
5|5|interviewer, the waiter, the doctor — holds the whole conversation in **English**,
6|6|and asks you questions on that topic. The moment you make a grammar or
7|7|word-choice mistake it corrects you in **Hinglish**, so you always understand
8|8|why: *"'He go' ki jagah 'He goes' bolna chahiye, kyunki he ke saath 's' lagta
9|9|hai."*
10|10|
11|11|Built for the ZenBricks take-home assignment, for Priyanka. **Only Sarvam AI models** are
12|12|used: Saaras v3 (speech-to-text), `sarvam-105b-conversations` (LLM),
13|13|Bulbul v3 (text-to-speech). No other model provider is involved.
14|14|
15|15|## What it does
16|16|
17|17|| # | Requirement | Where |
18|18||---|---|---|
19|19|| 1 | Voice in, voice out (STT → LLM → TTS) | `tutor.Tutor.turn()` |
20|20|| 2 | Understands Hindi and Hinglish; helps when the learner is stuck | stuck-learner rule in `SYSTEM_PROMPT`, answered in Hinglish |
21|21|| 3 | Role-played conversation on a learner-picked topic | persona per topic (interviewer, waiter, doctor…) + session loop |
22|22|| 4 | Corrects grammar/word-choice, explanation in Hinglish | English reply on `EN:`, Hinglish explanation on `HI:` |
23|23|| 5 | Adapts difficulty to the learner's level | confidence question in the first message sets `LEVEL`, re-judged every turn |
24|24|| 6 | Ends with a written summary: mistakes, corrections, 3 practice items | **End session** button |
25|25|| 7 | Simple UI | vanilla JS (`static/`) on a stdlib server (`server.py`) |
26|26|| + | Live transcript while you speak | `realtime.py`, the live panel above the mic |
27|27|
28|28|## Run it
29|29|
30|30|```bash
31|31|git clone https://github.com/astromanish/spoken-english-tutor.git
32|32|cd spoken-english-tutor
33|33|python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
34|34|
35|35|export SARVAM_API_KEY=...        # https://dashboard.sarvam.ai → API keys
36|36|.venv/bin/python server.py       # → http://127.0.0.1:7860
37|37|```
38|38|
39|39|Press **Start** and the tutor introduces its character, then asks how confident
40|40|you are speaking English — that answer sets how much it corrects you. Tap the
41|41|mic and speak (or type); the tutor replies aloud and keeps the conversation
42|42|going. **End session** writes the summary.
43|43|
44|44|While the mic is open, a live transcript of what Saaras hears appears above it;
45|45|press the mic again and that transcript becomes your turn.
46|46|
47|47|`ffmpeg` on your `PATH` converts the fallback recording (a browser upload posted
48|48|to `/api/turn`) into the 16 kHz WAV that Saaras expects; without it, WAV uploads
49|49|still work and the streaming path is unaffected.
50|50|
51|51|## Why these models
52|52|
53|53|- **Saaras v3 (STT)** — built for Indian languages and code-switching. A
54|54|  Hinglish sentence comes back as it was spoken instead of being mangled by an
55|55|  English-only transcriber. The live transcript uses `saaras:v3-realtime`, the
56|56|  same model over a websocket, so the words on screen are the words the turn
57|57|  runs on. Free API tier.
58|58|- **sarvam-105b-conversations (LLM)** — the `-conversations` variant returns
59|59|  the answer in `content`; the base `sarvam-105b` is a reasoning model that
60|60|  hides it in `reasoning_content` and breaks standard chat clients. Handles the
61|61|  English-conversation and Hinglish-correction mix in one call, and holds the
62|62|  role-play persona turn after turn. Free API tier.
63|63|- **Bulbul v3 (TTS)** — Indian-English and Hindi voices that pronounce the
64|64|  names and code-switched words correctly. Free API tier.
65|65|- **No UI framework** — the browser captures with Web Audio, plays the reply
66|66|  through an `<audio>` element, and talks to a handful of JSON endpoints
67|67|  (`/api/meta`, `/api/session`, `/api/turn`, `/api/summary`, `/api/stream/*`).
68|68|  `server.py` is `http.server` from the standard library, so the app's only
69|69|  dependencies are `requests`, `pyyaml` and `websockets`. Gradio was dropped
70|70|  because it pinned a large dependency tree for a UI that is one page of HTML.
71|71|
72|72|## Design decisions
73|73|
74|74|**English is the conversation, Hinglish is the correction.** The tutor plays a
75|75|character and speaks only English; the moment something is wrong — or the
76|76|learner is stuck — it switches to Hinglish (Hindi in Roman script, mixed with
77|77|English words) for that one line, then goes back to English:
78|78|
79|79|```
80|80|EN: You should say "He goes to school daily." What time do you reach office?
81|81|HI: 'He go' ki jagah 'He goes' bolna chahiye, kyunki he ke saath 's' lagta hai.
82|82|LEVEL: 1
83|83|```
84|84|
85|85|Lines are spoken in the order written. Both are Latin script, so both go to the
86|86|`en-IN` Bulbul voice, which reads code-mixed Indian English naturally; a line
87|87|that arrives in Devanagari is routed to `hi-IN` instead. Routing is by script,
88|88|not by the `EN:`/`HI:` tag, because the model sometimes drops the tag — and
89|89|neighbouring lines in the same language are merged into one TTS request.
90|90|
91|91|**Segments are synthesised in parallel.** Each language segment is its own TTS
92|92|request; they run concurrently and are stitched back in the written order, so an
93|93|English+Hinglish reply costs about its slowest segment instead of the sum, and one
94|94|slow call is retried rather than stalling the turn.
95|95|
96|96|**Level starts with a confidence question, not a dropdown.** The setup has no
97|97|level picker: the first message asks how confident he is speaking English, his
98|98|answer sets how hard the tutor comes down on grammar and word choice (1 = almost
99|99|every mistake, 2 = real mistakes plus better wording, 3 = fluency only), and the
100|100|tutor re-judges it every turn — reported on a `LEVEL:` line the parser reads
101|101|back for the badge.
102|102|
103|103|**The live transcript is the turn.** While the mic is open the page sends
104|104|250 ms of 16 kHz PCM to `POST /api/stream/<id>/audio`; `realtime.py` holds one
105|105|websocket to `saaras:v3-realtime` per recording and returns whatever
106|106|`transcript.partial` events have arrived, so the panel updates as the learner
107|107|speaks. The key stays on the server — the browser never opens a websocket of
108|108|its own, and no second port is needed. When the learner stops, a short silence
109|109|tail flushes the VAD and the `transcript.final` text is what the turn runs on,
110|110|so the words on screen are exactly the words the tutor corrects. A
111|111|`MediaRecorder` runs alongside as a fallback: if the stream yields nothing the
112|112|recording is uploaded and transcribed the old way.
113|113|
114|114|**Long recordings are chunked.** Saaras' REST endpoint caps files at 30 s, so
115|115|longer uploaded recordings are split with ffmpeg and the transcripts joined by
116|116|the stream instead.
117|117|
118|118|**Summary comes from the transcript.** Ending the session replays the whole
119|119|conversation to the model with a fixed summarisation prompt — no state to drift.
120|120|
121|121|**Transcripts are kept as spoken.** Saaras returns Hinglish in Devanagari
122|122|(`transcribe` mode), which is what the learner actually said; nothing is
123|123|silently translated.
124|124|
125|125|## Evaluation

`python eval_run.py` runs **9 scripted learner utterances** through the real
voice pipeline (TTS → STT → tutor → TTS) and a judge model grades each reply
against the expectation for that utterance.

**8/9 handled correctly. Average response time 5.2 s**
(STT 0.7 s · LLM 0.6 s · TTS 3.8 s) on an Intel i7-9750H / 8 GB / Linux, with
all three models on Sarvam's cloud — the latency is network + model time, not
local compute. A reply is an English line plus a Hinglish correction line, so
it is synthesised as two or three segments; those run in parallel and are
stitched in order, which is why TTS stays near a single call.

| # | Learner said | Verdict | Time |
|---|---|---|---|
| 1 | Mujhe English bolne mein thoda confidence nahi hai, beginner level par hoon. | ✅ | 5.3s |
| 2 | He go to school daily. | ✅ | 5.3s |
| 3 | I am agree with you. | ✅ | 4.2s |
| 4 | Yesterday I go to office and I am explain everything to my manager. | ✅ | 5.0s |
| 5 | mujhe samajh nahi aaya, aap phir se bolo | ❌ | 5.4s |
| 6 | She don't know nothing about the job. | ✅ | 6.0s |
| 7 | Main bahut nervous hoon, interview mein kya bolun? | ✅ | 5.3s |
| 8 | I am working in company from two years. | ✅ | 5.5s |
| 9 | Last weekend I travelled to Jaipur with my cousins and we tried the local street food. | ✅ | 4.4s |

Full table, per-turn timings and judge notes: [`eval/results.md`](eval/results.md)
(raw: `eval/results.json`). Reproduce with `python eval_run.py`.

The cases cover the confidence answer that sets the level (1), subject–verb
agreement (2, 6), "am + verb" (3), past tense (4, 8), a learner stuck in
Hinglish (5), a nervous learner who needs a sentence to say (7), and a clean
sentence where nothing should be corrected (9).

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
168|158|
169|159|```
170|160|server.py      HTTP server + JSON API (stdlib, no framework)
171|161|realtime.py    live transcription: PCM in over HTTP, one websocket to Saaras
172|162|static/        index.html, style.css, app.js — the whole UI
173|163|tutor.py       session state, tutor prompt, turn handling, summary
174|164|sarvam.py      the three Sarvam API clients + audio helpers
175|165|eval_run.py    scripted evaluation → eval/results.{json,md}
176|166|```
177|167|
178|168|## What I would improve next
179|169|
180|170|- **Latency:** TTS still dominates (~1.8 s even with parallel segments).
181|171|  Streaming the reply audio so playback starts on the first sentence, instead
182|172|  of waiting for the whole WAV, would cut the perceived gap again — the input
183|173|  side already streams.
184|174|- **True adaptation:** the level starts from his own confidence answer and the
185|175|  model re-judges it every turn, so the same mistake can be corrected hard early
186|176|  and left alone later; a spaced-repetition record of each mistake would make
187|177|  practice decisions durable instead of conversational.
188|178|- **Pronunciation feedback:** Saaras gives text, not phonetics — a scoring pass
189|179|  on the learner's actual audio would catch mispronounced words that are
190|180|  spelled correctly.
191|181|- **Offline mode:** everything runs on Sarvam's cloud today. A local Whisper +
192|182|  small Hindi-tuned TTS fallback would keep the tutor usable without a network.