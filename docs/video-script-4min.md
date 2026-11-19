# 4-minute demo video — shot script

**Deliverable:** 4:00 screen-recorded demo with voiceover, for LinkedIn / YouTube / X.
**Ratio:** 16:9, 1920×1080, 30 fps. Narration is 365 words ≈ 2:30 of speech, leaving ~1:30 for the
app's own audio — the tutor should be the loudest thing in the video, not you.

One line to keep you honest while recording: **you are not presenting a product, you
are showing a conversation going wrong and being fixed.** Every visual proves that.

---

## Pre-flight (10 minutes, before you hit record)

| | |
|---|---|
| **Record here** | `http://127.0.0.1:7860` — localhost is a secure context, so the mic works, and there is no cold start. Do **not** record on the free Render URL: it sleeps and costs you 30 s of black. |
| **Warm it up** | Open the app, pick the scenario, press Start, speak one full turn, then reload. First request of the day is slow; the recording should not be. |
| **Window** | Browser at 1440×900, page zoom 110%, bookmarks bar hidden, one tab only. Full-screen the window, then crop to the app in the edit. |
| **Voice** | Decide before you start: **Calm female** (`shreya`) or **Professional male** (`rahul`). The stage copy says *she/her* or *he/him* accordingly — you cannot mix them mid-recording. |
| **Notifications** | Focus / Do Not Disturb on. Close Mail, Slack, Messages. One popup ruins a live demo. |
| **Mic** | 15–20 cm, off-axis, gain peaking around −12 dB. Record 10 s and listen back before the real take. |
| **Cursor** | Move it out of frame when you are not clicking. Do not circle things with it. |
| **Takes** | Record the demo block twice: once where nothing goes wrong, once as the safety net. Cut between them. |

---

## Beat sheet

| Time | Screen | You say | Notes |
|---|---|---|---|
| 0:00–0:22 | Black → the app at rest (Start button, scenario picker, no cursor) | Hook, 3 sentences | Slow. No music yet. |
| 0:22–0:45 | Hover the scenario list, pick **Job interview**, voice picker visible | What it is | Title card at 0:24: *Spoken English Tutor — live, in a browser tab* |
| 0:45–1:05 | Press **Start**. Greeting plays. Confidence question. You answer **"Four."** | "No typing. It's listening the whole time." | Let the tutor's audio breathe — do not talk over it. Zoom 110% on the orb. |
| 1:05–1:35 | **The mistake turn** (see call sheet). Correction plays, then the Hinglish line, then the next question | "English for what to say, Hinglish for why." | **This is the money shot.** If the correction is missing, cut and re-record this turn only. |
| 1:35–1:55 | Start answering, then talk over him mid-sentence. Tutor goes quiet, pill flips to hearing | "If I cut in, it stops mid-sentence and listens." | Zoom on the status pill for 3 s in the edit. |
| 1:55–2:15 | Open the voice picker, press **Preview Voice** on a second voice | "Five voices. Same tutor, different people." | Only one preview — a full audition is 7 s of dead air. |
| 2:15–2:50 | Screen recording continues but slow: scroll the metric line, then a cut to a simple diagram or terminal | How it works — three stages + the ~1 s number | Text card at 2:38: **first sound ≈ 1.3 s** |
| 2:50–3:20 | Terminal: `node --test` passing, or the `[speak]` log lines | The parts that fought you | Optional b-roll. Keep it small and dark so it reads as code, not decoration. |
| 3:20–3:52 | Back to the app, mid-conversation, nothing staged | Who it's for + what's next | Say "free server" only if you are comfortable defending it. |
| 3:52–4:00 | End card: URL / "try it" line | CTA | Cut music hard at 4:00. |

---

## Narration (read this — 365 words, ~2:30)

> **0:00** You can study English for years and still freeze the moment someone actually
> speaks to you. Because the thing that fixes spoken English is not a course — it is a
> patient person who corrects you the second you get it wrong.
>
> I built that person. It lives in a browser tab.
>
> **0:24** You pick a scenario — job interview, doctor visit, ordering food — and then
> you just talk. It hears you, it plays the role, and every time you make a grammar
> mistake it stops and explains the fix in Hinglish — right before it asks you the
> next question.
>
> **0:45** No typing. No push-to-talk. The ear is open the whole time, and three quarters of a
> second of silence is the turn passing back to it.
>
> **1:05** That is a real correction. English for what to say, Hinglish for why — in a
> sentence short enough to remember.
>
> **1:35** And if I cut in, it stops mid-sentence and listens. It never talks over me.
>
> **1:57** Five voices. Same tutor, different people — you hear one before you commit.
>
> **2:15** Under the hood it is three stages. Speech recognition streams while I talk. A
> language model writes the English correction and the Hinglish why. Text to speech
> streams back instead of waiting for the whole reply. The first syllable reaches my
> ears about a second after my last word — and everything you have heard so far was
> generated live. No pre-recorded audio anywhere in this video.
>
> **2:50** The parts that fought me: turn-taking — thresholds tuned to measured speech
> levels instead of guesses; Hinglish — the same sentence spoken with an Indian accent
> but corrected in English; and a bug where the Hindi half of a correction was silently
> dropped for two days.
>
> **3:20** It runs in a browser, on a free server, for a fraction of a rupee per
> conversation. Next: more scenarios, a summary of the mistakes you actually made, and
> — the real goal — learners who are scared of English, not learners who are already
> good at it.
>
> **3:52** It is live. Pick a scenario, say something wrong, and tell me what breaks.

---

## Demo call sheet (rehearse this, do not improvise)

Scenario: **Job interview**. Tutor asks your confidence first — that is not a test, it
sets the correction level.

1. **Confidence answer:** say **"Four."** (one word, English). He sets the level and
   asks the first interview question.
2. **The mistake turn** — this exact sentence, it reliably produces two corrections:
   > "I am go to office yesterday and I am do the work."
   Expected shape of the reply: the corrected English sentence in quotes, a Hinglish
   line naming what was wrong (`go`/`do` tense), then the next question.
3. **Barge-in:** start answering, let him start replying to it, then talk over him
   after his first few words. Watch the pill flip from *Speaking* to *Listening to
   you* and his voice stop. Pause, then finish your sentence so the take ends clean.
4. **Preview:** voice picker → another voice → **Preview Voice**. Wait for
   *Everything ready* before moving on.

**All three lines below were run against the live app before this script was written**
(corrections quoted are the actual output). Keep them verbatim — the demo is not the
place to improvise a grammar error:

| You say | What comes back |
|---|---|
| "Four." | No acknowledgement — he goes straight into the interview. That is correct behaviour: the answer sets the level, it is not corrected. |
| "I am go to office yesterday and I am do the work." | Correction in quotes + `'Go' aur 'do' ki jagah past tense 'went' aur 'did' use karo.` + next question |
| "I am working here since two years." | `"I have been working here for two years."` + Hinglish line on present perfect continuous |

**If a turn comes back with no correction** — the model can let one through. Do not fudge
it in the edit and do not re-explain it yourself. Say the backup line
*"I am working here since two years."* and carry on; it fires every time.

**If the turn-taking cuts you off** mid-thought, that is the 750 ms window doing its
job. Finish the sentence in the same breath, or end the utterance on purpose — do not
restart from the top of the take.

---

## Two alternate hooks (LinkedIn tests better with the second)

1. *"You can study English for years and still freeze when someone speaks to you."*
2. *"This is me practising a job interview. The person correcting me is not a person."*
   — then cut straight to the demo, save the explainer for 1:00.

## Captions

> Built a spoken English tutor that actually talks back: role-play scenarios, real-time
> corrections, Hinglish explanations for *why* the sentence was wrong.
>
> Runs in a browser tab. First sound ~1.3 s after you stop talking. Demo is unedited.

## Edit notes

- Music: none under 0:45–2:15 — the tutor's voice is the content. A quiet bed at
  −24 dB under the talky sections only.
- Three text cards, no more: title (0:24), `first sound ≈ 1.3 s` (2:38), CTA (3:52).
- One zoom per beat, on the thing being described: orb → pill → voice list → metric.
- Do not speed up the demo. If the video is 4:00 and 1:50 of it is the app talking
  slowly, that is the point.
