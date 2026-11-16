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
CASES = [
    ("Hello, main aaj office ja raha hoon. Kal ek meeting hai.", "en-IN",
     "Understands Hinglish, replies in English, keeps the conversation going."),
    ("He go to school daily.", "en-IN",
     "Corrects to 'He goes to school daily' and explains in Hindi."),
    ("I am agree with you.", "en-IN",
     "Corrects to 'I agree with you' and explains in Hindi."),
    ("Yesterday I go to office and I am explain everything to my manager.", "en-IN",
     "Catches the tense mistakes (went / explained), corrects them, explains briefly in Hindi."),
    ("mujhe samajh nahi aaya, aap phir se bolo", "hi-IN",
     "Learner stuck in Hindi: explains in Hindi and steers back to English with the next question."),
    ("She don't know nothing about the job.", "en-IN",
     "Corrects the double negative / agreement ('She doesn't know') with a short Hindi explanation."),
    ("Main bahut nervous hoon, interview mein kya bolun?", "hi-IN",
     "Encouraging, answers in a mix that unblocks the learner, then continues the interview practice in English."),
    ("I am working in company from two years.", "en-IN",
     "Corrects to 'I have been working ... for two years' (or 'I have worked ... for') with a Hindi explanation."),
    ("Last weekend I travelled to Jaipur with my cousins and we tried the local street food.", "en-IN",
     "Nothing to correct: responds to the content naturally, keeps the conversation going, and may raise the difficulty."),
]

JUDGE_PROMPT = """You grade a spoken-English tutor's reply to one learner utterance.
Return one word: PASS or FAIL, then a short reason (max 20 words).

PASS requires ALL of the expectation below being met. The tutor speaks English,
may add a short Hindi explanation, and must not ignore the learner's problem.
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
        t0 = time.time()
        audio = sarvam.speak(text, language_code=lang)
        turn = tutor.turn(audio_path=audio)
        wall = int((time.time() - t0) * 1000)

        ok, reason = judge(text, turn.spoken_text, expectation)
        rows.append({
            "n": i, "said": text, "heard": turn.heard, "tutor": turn.spoken_text,
            "expected": expectation, "pass": ok, "reason": reason,
            "level": turn.level, "ms_stt": turn.ms_stt, "ms_llm": turn.ms_llm,
            "ms_tts": turn.ms_tts, "ms_total": turn.ms_total, "ms_wall": wall,
        })
        print(f"[{i}/{len(CASES)}] {'PASS' if ok else 'FAIL'}  "
              f"{turn.ms_total/1000:.1f}s  said={text[:46]!r}", flush=True)

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
