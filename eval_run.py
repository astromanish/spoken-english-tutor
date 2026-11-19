"""Scripted evaluation: 9 learner utterances through the real voice pipeline.

Each utterance is spoken with Sarvam TTS, transcribed by Saaras v3, answered by
the tutor (sarvam-105b-conversations), and spoken back with Bulbul v3. A judge
model scores whether the tutor handled it correctly. Results land in
eval/results.json and eval/results.md.

Run:  python eval_run.py
"""

from __future__ import annotations

import json
import os
import time

import sarvam
from tutor import Tutor

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "eval")

# (utterance, language for synthesising it, what a correct tutor reply must do)
# The conversation is role-played in English; corrections and stuck-moments
# are explained in Hinglish (Hindi in Roman script).
CASES = [
    ("Mujhe English bolne mein thoda confidence nahi hai, beginner level par hoon.", "hi-IN",
     "Takes the confidence answer, reports a level, and starts the role-play by asking the first interview question in English."),
    ("He go to school daily.", "en-IN",
     "Stays in English as the character, quotes the full corrected sentence \"He goes to school daily.\" and explains the -s for 'he' in Hinglish (Roman-script Hindi)."),
    ("I am agree with you.", "en-IN",
     "Quotes a corrected form of his sentence — \"I agree with you.\" or \"I agree.\" — explains in Hinglish that 'agree' is already a verb, then continues the conversation in English."),
    ("Yesterday I go to office and I am explain everything to my manager.", "en-IN",
     "Quotes a corrected sentence using the past tense (went / explained), explains it briefly in Hinglish, and keeps the conversation going in English."),
    ("mujhe samajh nahi aaya, aap phir se bolo", "hi-IN",
     "Learner stuck in Hinglish: unblocks him in Hinglish, gives the English sentence to repeat in double quotes, then continues the role-play in English."),
    ("She don't know nothing about the job.", "en-IN",
     "Quotes a corrected sentence such as \"She doesn't know anything about the job.\" or \"She does not know anything about the job.\" and explains the double negative in Hinglish."),
    ("Main bahut nervous hoon, interview mein kya bolun?", "hi-IN",
     "Encourages him and quotes a short English sentence he can use in the interview, staying in the interviewer role."),
    ("I am working in company from two years.", "en-IN",
     "Quotes a correct present-perfect form — \"I have been working in a company for two years.\" or \"... in the company for two years\" (or 'I have worked ... for') — with a Hinglish explanation."),
    ("Last weekend I travelled to Jaipur with my cousins and we tried the local street food.", "en-IN",
     "Nothing to correct: responds in English as the character, may quote a richer English version, keeps the conversation going."),
]

JUDGE_PROMPT = """You grade a spoken-English tutor's reply to one learner utterance in a ROLE-PLAY conversation.
The tutor speaks English as the character; grammar and word-choice corrections (and unblocking a stuck learner) are explained in HINGLISH — Hindi written in Roman script, mixed with English words, e.g. "'He go' ki jagah 'He goes' bolna chahiye."
Return one word: PASS or FAIL, then a short reason (max 20 words).

PASS requires ALL of these being met:
- the reply is in English as the character, with Hinglish only for the correction or unblock line — never a whole reply in Devanagari Hindi,
- when the expectation calls for a correction, the corrected English sentence appears inside double quotes (with or without a "You should say" prefix) and the explanation is in Hinglish — that is Hindi words written in Roman script, mixed into English. Any Hindi-in-Latin-script phrasing counts as Hinglish, including a single clause such as "'He go' ki jagah 'He goes' bolna chahiye, kyunki third person singular mein 's' lagta hai." Do not fail a reply because the Hinglish is short, or because the quotes follow a comma rather than a colon.
- when the learner is stuck or nervous and the expectation asks for encouragement, Hinglish encouragement plus one English sentence in quotes satisfies it; that case needs no "correction" explanation,
- the expectation below is met, and the learner's problem is not ignored.
Reply as: PASS/FAIL — <reason>"""

# ── judge ────────────────────────────────────────────────────────────────

def judge(utterance: str, reply: str, expectation: str) -> tuple[bool, str]:
    verdict = sarvam.chat(
        [{"role": "system", "content": JUDGE_PROMPT},
         {"role": "user",
          "content": f"Learner said: {utterance}\n\nTutor replied: {reply}\n\n"
                     f"Expectation: {expectation}"}],
        temperature=0.0, max_tokens=120,
    )
    ok = verdict.strip().upper().startswith("PASS")
    return ok, verdict.strip().replace("\n", " ")[:220]


# ── run ──────────────────────────────────────────────────────────────────

def run() -> dict:
    os.makedirs(OUT_DIR, exist_ok=True)
    tutor = Tutor(topic="Job interview", level=1)
    rows = []

    for i, (text, lang, expectation) in enumerate(CASES, 1):
        # 1. speak the scripted utterance, 2. run it through the tutor
        try:
            t0 = time.time()
            audio = sarvam.speak(text, language_code=lang)
            turn = tutor.turn(audio_path=audio)
            wall = int((time.time() - t0) * 1000)
            # judge the raw reply: the LEVEL: line is stripped from what is
            # spoken, and case 1 is graded on the tutor reporting a level
            raw = tutor.history[-1]["content"]
            ok, reason = judge(text, raw, expectation)
            row = {
                "n": i, "said": text, "heard": turn.heard, "tutor": turn.full_text,
                "expected": expectation, "pass": ok, "reason": reason,
                "level": turn.level, "ms_stt": turn.ms_stt, "ms_llm": turn.ms_llm,
                "ms_tts": turn.ms_tts, "ms_total": turn.ms_total, "ms_wall": wall,
            }
        except Exception as e:  # one bad case must not kill the run
            row = {"n": i, "said": text, "heard": "", "tutor": "",
                   "expected": expectation, "pass": False,
                   "reason": f"ERROR {type(e).__name__}: {e}",
                   "level": tutor.level, "ms_stt": 0, "ms_llm": 0, "ms_tts": 0,
                   "ms_total": 0, "ms_wall": 0}
        rows.append(row)
        print(f"[{i}/{len(CASES)}] {'PASS' if row['pass'] else 'FAIL'}  "
              f"{row['ms_total']/1000:.1f}s  said={text[:46]!r}  {row['reason'][:70]}",
              flush=True)
        time.sleep(3.0)   # pace the burst — Saaras answers 400 on bursts

    passed = sum(r["pass"] for r in rows)
    n = len(rows)
    result = {
        "model_stt": sarvam.STT_MODEL, "model_chat": sarvam.CHAT_MODEL,
        "model_tts": sarvam.TTS_MODEL, "cases": n, "passed": passed,
        "avg_ms_total": round(sum(r["ms_total"] for r in rows) / n),
        "avg_ms_stt": round(sum(r["ms_stt"] for r in rows) / n),
        "avg_ms_llm": round(sum(r["ms_llm"] for r in rows) / n),
        "avg_ms_tts": round(sum(r["ms_tts"] for r in rows) / n),
        "rows": rows,
    }
    with open(os.path.join(OUT_DIR, "results.json"), "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    with open(os.path.join(OUT_DIR, "results.md"), "w") as f:
        f.write(render(result))
    print(f"\n{passed}/{n} correct · avg response "
          f"{result['avg_ms_total']/1000:.1f}s "
          f"(STT {result['avg_ms_stt']/1000:.1f}s + LLM "
          f"{result['avg_ms_llm']/1000:.1f}s + TTS {result['avg_ms_tts']/1000:.1f}s)")
    return result


def render(r: dict) -> str:
    lines = [
        "# Evaluation results", "",
        f"**{r['passed']}/{r['cases']} handled correctly.** "
        f"Average response time **{r['avg_ms_total']/1000:.1f}s** "
        f"(STT {r['avg_ms_stt']/1000:.1f}s · LLM {r['avg_ms_llm']/1000:.1f}s · "
        f"TTS {r['avg_ms_tts']/1000:.1f}s) on this machine.", "",
        f"Models: STT `{r['model_stt']}` · chat `{r['model_chat']}` · "
        f"TTS `{r['model_tts']}`.", "",
        "| # | Learner said | What the tutor did | Verdict | Time |",
        "|---|---|---|---|---|",
    ]
    for row in r["rows"]:
        reply = row["tutor"].replace("|", "/").replace("\n", " ")
        if len(reply) > 130:
            reply = reply[:127] + "…"
        said = row["said"].replace("|", "/")
        lines.append(f"| {row['n']} | {said} | {reply} | "
                     f"{'✅ PASS' if row['pass'] else '❌ FAIL'} | "
                     f"{row['ms_total']/1000:.1f}s |")
    lines += ["", "## Judge notes", ""]
    for row in r["rows"]:
        lines.append(f"- **{row['n']}** — {row['reason']}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    run()
