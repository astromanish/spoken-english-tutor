# Spoken English Tutor

A live voice tutor for Hindi speakers learning spoken English. Pick a scenario — job
interview, doctor visit, ordering food — and talk: the tutor plays the other person,
corrects grammar the moment a mistake happens, explains why in Hinglish, and keeps the
conversation going. No typing, no push-to-talk, no client framework.

Sarvam models only: `saaras:v3` (STT) · `sarvam-105b-conversations` (LLM) · `bulbul:v3`
(TTS). One Python process, stdlib HTTP server, Web Audio in the browser.

> No authentication: a publicly reachable instance spends the API key. Run it locally.

---

## Setup

**You need:** Python 3.12 and a [Sarvam API key](https://dashboard.sarvam.ai). Node is only
for the JavaScript tests; ffmpeg is only for long-recording fallbacks.

```bash
git clone git@github.com:astromanish/spoken-english-tutor.git && cd spoken-english-tutor
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
printf 'SARVAM_API_KEY=your-key-here\n' > .env && chmod 600 .env
./run.sh                                                          # → http://127.0.0.1:7860
```

Open the URL, allow the microphone, pick a scenario, press **Start**, answer the
confidence question (1–5) and the role-play begins. 750 ms of quiet hands the turn back.

```bash
node --test                                    # 17 turn-taking + WAV tests, offline, no mic
.venv/bin/python eval_run.py                   # 9 scripted utterances, judged → eval/
.venv/bin/python scripts/measure_latency.py 3  # live turn latency (server must be running)
```

---

## Design decisions

**Conversation is English, corrections are Hinglish.** The tutor stays in character in
English; a correction switches to Roman-script Hindi mixed with English for exactly that
line. The learner is told what to say *and* why.

**A correction is its own message.** A question buried inside a correction is what gets
remembered instead of the fix, so a `NEXT:` marker splits every reply into
correction-then-question. Both halves synthesise in parallel: a turn costs the slower half,
not the sum.

**The transcript keeps the mistake.** `mode=codemix` transcribes what was said —
`"She don't know nothing"` stays a double negative. Measured over 6 recordings of one
deliberately wrong sentence, `transcribe` silently repaired the grammar in **2 of 6**
(erasing the thing to correct); `verbatim` turned English into Devanagari (unquotable).

**TTS routing follows the script, not the tag.** `EN:` and Roman `HI:` lines both go to the
`en-IN` voice, which reads code-mixed Indian English naturally; Devanagari goes to `hi-IN`.
The model drops tags, so script is the reliable signal.

**Level is inferred, never configured.** The opening question asks for confidence 1–5; that
sets strictness (1–2 → almost everything; 3 → real mistakes; 4–5 → naturalness only), words
count as answers, and it is re-judged each turn on a `LEVEL:` line. No settings screen.

**The ear never closes; 750 ms of silence ends a turn.** Energy VAD in 128 ms blocks, gates
calibrated by measurement (speech ≈ 0.09 RMS, quiet room ≈ 0.002), one stream per utterance,
next stream opened before the current turn is awaited — never deaf while thinking or
speaking. A doubled gate during playback means only real speech interrupts it.

**Speech streams; nothing waits for a finished file.** REST TTS returns nothing until the
whole WAV is rendered (2.2–3.3 s). `/speak/<token>` relays Bulbul's websocket as chunked
`linear16` PCM and the client schedules each chunk on the audio graph: first sound ≈1.0 s,
barge-in is `source.stop()`, and no codec is required — PCM sidesteps browsers and CI
Chromium builds that ship without an MP3 decoder.

**Turn-taking is DOM-free by design.** The silence rule and the merge/hold logic live in
`static/vad.js` and `static/turns.js` with no DOM access, so the part of a voice UI that
cannot be heard in CI is the part that is unit-tested.

**One process, cookie-keyed sessions, keys server-side.** Capped in-memory session map,
`_sid` cookie per browser, API key never reaches the client. The browser builds its own WAV
header (`static/wav.js`), so no ffmpeg is needed on the host.

**No summary for an empty conversation.** With zero learner turns the model is not called —
asked to summarise a one-sided conversation it invents mistakes. Failures surface as one
sentence to the learner; details go to the console.

---

## Evaluation results

### Correctness — 9/9

Each case is spoken with Bulbul, transcribed by Saaras, answered by the tutor, then graded
against a written expectation by a judge model. Transcripts and judge notes:
[`eval/results.md`](eval/results.md) · reproduce: `eval_run.py`.

| Learner utterance | Behaviour verified |
|---|---|
| "Mujhe English bolne mein confidence nahi hai, beginner level par hoon." | confidence answer read as level, not corrected as grammar |
| "He go to school daily." | quoted correction + third-person `-s` explained |
| "I am agree with you." | quoted correction + `agree` is already a verb |
| "Yesterday I go to office and I am explain everything to my manager." | past tense corrected in full |
| "mujhe samajh nahi aaya, aap phir se bolo" | Hinglish unblock, re-asked in simpler English |
| "She don't know nothing about the job." | double negative corrected and explained |
| "Main bahut nervous hoon, interview mein kya bolun?" | Hinglish reassurance + a sentence to use |
| "I am working in company from two years." | present perfect continuous, Hinglish reason |
| "Last weekend I travelled to Jaipur with my cousins…" | nothing to correct — reacts, no invented mistake |

**Disclosure.** The judge is an LLM; its first pass scored **6/9 on replies that read as
correct to a human** — it denied a quote that was present and demanded a correction where
none existed. Two fixes followed: the grading prompt now defines quoting and Hinglish
explicitly, and one real defect was fixed in the tutor (a confidence answer in words was
being grammar-corrected). So 9/9 reflects current code **and** a clarified grader — a
behavioural check over 9 hand-written cases, not an accuracy figure.

### Latency — interactive path

Three consecutive turns through the endpoints the browser uses, 3.5 s utterance
(`scripts/measure_latency.py 3`):

| stage | mean | spread |
|---|---|---|
| STT — turn closes → final transcript | **360 ms** | 350–373 |
| LLM — transcript → reply + speech segments | **268 ms** | 241–284 |
| TTS — request → first PCM chunk | **405 ms** | 387–425 |
| **first sound** | **1 034 ms** | 1 018–1 059 |

The 750 ms silence window is excluded — that is the learner's pause, not cost; add it for
wall-clock from the last word (≈1.8 s). The batch path used by the eval harness, where the
whole reply is rendered before returning, averages **4.5 s** per turn, which is why the UI
never takes that path.

### Not covered

Barge-in under real room noise, recognition on heavy accents or quiet microphones,
subjective quality of the Hinglish voice, drift past 20 turns. All three models run on
Sarvam's cloud, so the latency above is network plus model time, not local compute.
