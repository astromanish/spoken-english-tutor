"""Gradio UI — voice in, voice out spoken-English tutor."""

from __future__ import annotations

import gradio as gr

from tutor import LEVELS, TOPICS, Tutor, plain_reply

GREETING = (
    "Pick a topic and a level, then press **Start**. "
    "Speak into the microphone (or type) and the tutor replies aloud."
)


def start(topic: str, level: int):
    try:
        t = Tutor(topic=topic, level=int(level))
    except Exception as e:
        return chat, None, "", f"⚠️ {e}", None, ""
    chat = [{"role": "assistant", "content": t.greeting}]
    return t, chat, _level_md(t.level), "✅ Session started — speak or type below."


def send(audio, text, t: Tutor | None, chat: list):
    if t is None:
        return chat, None, "", "⚠️ Press **Start** first.", None, ""
    if not audio and not (text or "").strip():
        return chat, None, _level_md(t.level), "⚠️ Say something first.", None, ""
    try:
        turn = t.turn(audio_path=audio,
                      text=None if audio else (text.strip() or None))
    except Exception as e:
        return chat, None, _level_md(t.level), f"⚠️ {e}", None, ""
    chat = list(chat or []) + [
        {"role": "user", "content": turn.heard},
        {"role": "assistant", "content": turn.spoken_text},
    ]
    status = (
        f"🎙 STT {turn.ms_stt/1000:.1f}s · 🧠 LLM {turn.ms_llm/1000:.1f}s · "
        f"🔊 TTS {turn.ms_tts/1000:.1f}s · total {turn.ms_total/1000:.1f}s"
    )
    return chat, turn.audio_path, _level_md(turn.level), status, None, ""


def end_session(t: Tutor | None, chat: list):
    if t is None:
        return chat, "⚠️ No active session."
    try:
        md = t.summary()
    except Exception as e:
        return chat, f"⚠️ Summary failed: {e}"
    chat = list(chat or []) + [{"role": "assistant", "content": "**Session ended — your written summary is below.**"}]
    return chat, md


def _level_md(level: int) -> str:
    return f"**Level {level} · {LEVELS.get(level, '?')}**"


with gr.Blocks(title="Spoken English Tutor") as demo:
    gr.Markdown("# 🗣 Spoken English Tutor")
    gr.Markdown(GREETING)

    with gr.Row():
        topic = gr.Dropdown(TOPICS, value=TOPICS[0], label="Topic", scale=3)
        level = gr.Dropdown(
            [(f"{k} · {v}", k) for k, v in LEVELS.items()], value=1,
            label="Starting level", scale=1,
        )
        start_btn = gr.Button("Start", variant="primary", scale=1)

    level_md = gr.Markdown(_level_md(1))
    chatbot = gr.Chatbot(label="Session", height=420)

    with gr.Row():
        mic = gr.Audio(sources=["microphone", "upload"], type="filepath",
                       label="Speak", scale=3)
        typed = gr.Textbox(label="…or type", scale=2, lines=1,
                           placeholder="Type if you cannot speak right now")
        send_btn = gr.Button("Send", variant="primary", scale=1)

    audio_out = gr.Audio(label="Tutor replies aloud", autoplay=True)
    status = gr.Markdown("")
    end_btn = gr.Button("End session — get written summary")
    summary = gr.Markdown("")

    session = gr.State(None)

    start_btn.click(start, [topic, level], [session, chatbot, level_md, status])
    send_btn.click(send, [mic, typed, session, chatbot],
                   [chatbot, audio_out, level_md, status, mic, typed])
    typed.submit(send, [mic, typed, session, chatbot],
                 [chatbot, audio_out, level_md, status, mic, typed])
    end_btn.click(end_session, [session, chatbot], [chatbot, summary])


if __name__ == "__main__":
    demo.launch(server_name="127.0.0.1", server_port=7860)
