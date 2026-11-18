/* Spoken English Tutor — vanilla JS UI. Talks to server.py over:
   GET  /api/meta, POST /api/session, POST /api/turn, POST /api/summary,
   POST /api/stream/start · /api/stream/<id>/audio · /api/stream/<id>/stop
   (the stream endpoints carry live PCM to Sarvam's realtime STT). */

const $ = (id) => document.getElementById(id);

const els = {
  topic: $('topic'),
  start: $('start'),
  badge: $('badge'),
  status: $('status'),
  chat: $('chat'),
  mic: $('mic'),
  typed: $('typed'),
  send: $('send'),
  player: $('player'),
  end: $('end'),
  summaryCard: $('summaryCard'),
  summary: $('summary'),
  live: $('live'),
  liveText: $('liveText'),
  liveLang: $('liveLang'),
};

let started = false;
let busy = false;
let stopping = false; // true while a recording is being finalised
let rec = null; // the active microphone recording, while it is open
let flushing = null; // promise chain that keeps audio uploads in order

/* ── tiny markdown renderer ─────────────────────────────────────────────── */

const escapeHtml = (s) =>
  s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function inline(s) {
  return s
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[\s(])\*([^*\n]+)\*/g, '$1<em>$2</em>');
}

function markdown(src, bump = 0) {
  const lines = escapeHtml(src || '').split('\n');
  let html = '';
  let list = null;

  const closeList = () => {
    if (list) {
      html += `</${list}>`;
      list = null;
    }
  };

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) {
      closeList();
      continue;
    }
    // an indented line under a bullet is that bullet's continuation, not a new one
    if (/^\s+\S/.test(raw) && list && html.endsWith('</li>')) {
      html = `${html.slice(0, -'</li>'.length)} ${inline(line)}</li>`;
      continue;
    }
    let m;
    if ((m = line.match(/^(#{1,6})\s+(.*)$/))) {
      closeList();
      const n = Math.min(m[1].length + bump, 6); // keep headings sized for the card
      html += `<h${n}>${inline(m[2])}</h${n}>`;
    } else if ((m = line.match(/^[-*]\s+(.*)$/))) {
      if (list !== 'ul') {
        closeList();
        html += '<ul>';
        list = 'ul';
      }
      html += `<li>${inline(m[1])}</li>`;
    } else if ((m = line.match(/^\d+\.\s+(.*)$/))) {
      if (list !== 'ol') {
        closeList();
        html += '<ol>';
        list = 'ol';
      }
      html += `<li>${inline(m[1])}</li>`;
    } else {
      closeList();
      html += `<p>${inline(line)}</p>`;
    }
  }
  closeList();
  return html;
}

/* ── view helpers ───────────────────────────────────────────────────────── */

function setStatus(text, warn = false) {
  els.status.textContent = text;
  els.status.classList.toggle('warn', warn);
}

/* The level is not picked any more: the tutor asks how confident he is in
   English and sets it from the answer, so the badge waits for that answer. */
function setBadgeFrom(data) {
  els.badge.textContent = data.awaiting_confidence
    ? 'Answer the confidence question'
    : `Level ${data.level} · ${data.level_name}`;
}

function addMessage(role, text) {
  const empty = els.chat.querySelector('.empty');
  if (empty) empty.remove();

  const div = document.createElement('div');
  div.className = `msg ${role}`;
  const who = document.createElement('span');
  who.className = 'who';
  who.textContent = role === 'user' ? 'You' : 'Tutor';
  div.appendChild(who);
  div.insertAdjacentHTML('beforeend', markdown(text, 2));

  els.chat.appendChild(div);
  els.chat.scrollTop = els.chat.scrollHeight;
}

function clearChat(placeholder = 'No session yet — press Start.') {
  els.chat.innerHTML = '';
  const p = document.createElement('p');
  p.className = 'empty';
  p.textContent = placeholder;
  els.chat.appendChild(p);
}

function setBusy(on) {
  busy = on;
  els.send.disabled = on;
  els.start.disabled = on;
  els.end.disabled = on;
  els.typed.disabled = on;
  els.mic.disabled = on;
}

/* Two messages play in order: the correction first, then the question, so
   the learner hears the fix before he is asked anything. */
let nextAudio = null;

function playOne(url) {
  els.player.src = url;
  els.player.play().catch(() => {
    /* autoplay blocked or decode error — the transcript still has the text */
  });
}

function play(url, url2) {
  nextAudio = url2 || null;
  if (url) return playOne(url);
  if (nextAudio) {
    const n = nextAudio;
    nextAudio = null;
    playOne(n);
  }
}

els.player.addEventListener('ended', () => {
  if (!nextAudio) return;
  const n = nextAudio;
  nextAudio = null;
  playOne(n);
});

function timings(t) {
  const s = (ms) => (ms / 1000).toFixed(1);
  return `🎙 STT ${s(t.stt)}s · 🧠 LLM ${s(t.llm)}s · 🔊 TTS ${s(t.tts)}s · total ${s(t.total)}s`;
}

async function postJson(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

/* ── setup ──────────────────────────────────────────────────────────────── */

async function loadMeta() {
  try {
    const res = await fetch('/api/meta');
    if (!res.ok) throw new Error(`meta ${res.status}`);
    const meta = await res.json();

    els.topic.innerHTML = meta.topics
      .map((t) => `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`)
      .join('');
  } catch (e) {
    setStatus(`⚠️ Could not load topics: ${e.message}`, true);
  }
}

/* ── start ──────────────────────────────────────────────────────────────── */

async function startSession() {
  setBusy(true);
  setStatus('Connecting to the tutor…');
  els.summaryCard.hidden = true;
  els.summary.innerHTML = '';

  try {
    const data = await postJson('/api/session', { topic: els.topic.value });
    started = true;
    clearChat();
    addMessage('tutor', data.greeting);
    setBadgeFrom(data);
    setStatus('✅ Session started — speak or type below.');
  } catch (e) {
    started = false;
    setStatus(`⚠️ ${e.message}`, true);
  } finally {
    setBusy(false);
    els.typed.focus();
  }
}

/* ── one learner turn ───────────────────────────────────────────────────── */

async function runTurn(request) {
  if (!started) {
    setStatus('⚠️ Press Start first.', true);
    return;
  }
  if (busy) return;

  setBusy(true);
  setStatus('Thinking…');
  try {
    const res = await request();
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);

    addMessage('user', data.heard);
    addMessage('tutor', data.reply);
    if (data.reply2) addMessage('tutor', data.reply2); // the question, after
    setBadgeFrom(data);
    play(data.audio, data.audio2);
    setStatus(timings(data.timings));
  } catch (e) {
    setStatus(`⚠️ ${e.message}`, true);
  } finally {
    setBusy(false);
    els.typed.focus();
  }
}

function sendTyped() {
  const text = els.typed.value.trim();
  if (!text) {
    setStatus('⚠️ Say something first.', true);
    return;
  }
  els.typed.value = '';
  runTurn(() =>
    fetch('/api/turn', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    }),
  );
}

function sendAudio(blob) {
  if (!blob || !blob.size) {
    setStatus('⚠️ Nothing recorded — try again.', true);
    return;
  }
  runTurn(() =>
    fetch('/api/turn', {
      method: 'POST',
      headers: { 'Content-Type': blob.type || 'audio/webm' },
      body: blob,
    }),
  );
}

/* ── microphone + live transcription ────────────────────────────────────── */

const STT_RATE = 16000; // Saaras realtime expects linear16 mono at 16 kHz
const FLUSH_MS = 250; // how much audio each upload carries

function pickMime() {
  const options = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];
  return options.find((m) => window.MediaRecorder && MediaRecorder.isTypeSupported(m)) || '';
}

function setRecording(on) {
  els.mic.classList.toggle('recording', on);
  els.mic.textContent = on ? '⏹' : '🎙';
  els.mic.title = on ? 'Stop and send' : 'Record from the microphone';
  els.typed.disabled = on || busy;
  els.send.disabled = on || busy;
}

function showLive(on) {
  els.live.hidden = !on;
  els.live.classList.remove('done');
  if (!on) {
    els.liveText.textContent = '';
    els.liveLang.textContent = '';
  }
}

function renderLive(data) {
  if (data.error) {
    setStatus(`⚠️ Live transcription: ${data.error}`, true);
    return;
  }
  const text = (data.text || '').trim();
  const caret = '<span class="caret"></span>';
  els.liveText.classList.toggle('quiet', !text);
  els.liveText.innerHTML = text ? escapeHtml(text) + caret : 'Listening…' + caret;
  els.liveLang.textContent = data.language || '';
  els.live.classList.toggle('done', Boolean(data.final));
}

/* 16-bit little-endian PCM, resampled to 16 kHz if the context refused it. */
function resample(samples, from, to) {
  if (from === to) return samples;
  const ratio = to / from;
  const out = new Float32Array(Math.floor(samples.length * ratio));
  for (let i = 0; i < out.length; i++) {
    const pos = i / ratio;
    const i0 = Math.floor(pos);
    const i1 = Math.min(i0 + 1, samples.length - 1);
    const frac = pos - i0;
    out[i] = samples[i0] * (1 - frac) + samples[i1] * frac;
  }
  return out;
}

function toPcm16(samples, from = STT_RATE) {
  const res = resample(samples, from, STT_RATE);
  const pcm = new Int16Array(res.length);
  for (let i = 0; i < res.length; i++) {
    const s = Math.max(-1, Math.min(1, res[i]));
    pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return new Uint8Array(pcm.buffer);
}

/* Upload the audio captured since the last flush and paint the new text. */
function flushAudio() {
  if (!rec || !rec.pending.length) return Promise.resolve();
  const parts = rec.pending;
  const id = rec.id;
  rec.pending = [];
  const body = new Blob(parts, { type: 'application/octet-stream' });

  flushing = (flushing || Promise.resolve()).then(async () => {
    try {
      const res = await fetch(`/api/stream/${id}/audio`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/octet-stream' },
        body,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || `stream ${res.status}`);
      if (rec && rec.id === id) renderLive(data);
    } catch (e) {
      setStatus(`⚠️ Live transcription dropped: ${e.message}`, true);
    }
  });
  return flushing;
}

async function startListening() {
  stopping = false; // self-heal if a previous stop threw before clearing it
  let media;
  try {
    media = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    setStatus(`⚠️ Microphone unavailable: ${e.message}`, true);
    return;
  }

  let id;
  try {
    ({ id } = await postJson('/api/stream/start'));
  } catch (e) {
    media.getTracks().forEach((t) => t.stop());
    setStatus(`⚠️ Live transcription unavailable: ${e.message}`, true);
    return;
  }

  let ctx;
  try {
    ctx = new AudioContext({ sampleRate: STT_RATE });
  } catch (e) {
    ctx = new AudioContext(); // older browsers: resample in toPcm16
  }
  // A real mic click carries user activation, so this resolves; if the browser
  // keeps the context suspended we still get the MediaRecorder fallback below.
  ctx.resume().catch(() => {});

  const source = ctx.createMediaStreamSource(media);
  const processor = ctx.createScriptProcessor(4096, 1, 1);
  const mute = ctx.createGain();
  mute.gain.value = 0; // keeps the graph alive without echoing the mic

  const r = { id, ctx, media, source, processor, mute, pending: [], chunks: [], recorder: null };
  processor.onaudioprocess = (e) => {
    if (rec !== r) return;
    r.pending.push(toPcm16(e.inputBuffer.getChannelData(0), ctx.sampleRate));
  };
  source.connect(processor);
  processor.connect(mute);
  mute.connect(ctx.destination);

  // Plain MediaRecorder alongside the stream: only used if the live
  // transcript comes back empty, so the learner never loses their turn.
  const mime = pickMime();
  r.mime = (mime || 'audio/webm').split(';')[0];
  try {
    r.recorder = new MediaRecorder(media, mime ? { mimeType: mime } : undefined);
    r.recorder.ondataavailable = (e) => {
      if (e.data && e.data.size) r.chunks.push(e.data);
    };
    r.recorder.start();
  } catch (e) {
    r.recorder = null;
  }

  rec = r;
  r.timer = setInterval(flushAudio, FLUSH_MS);

  setRecording(true);
  showLive(true);
  renderLive({ text: '' });
  setStatus('● Recording — the live transcript appears here; click the mic to send.');
}

function stopFallback(r) {
  return new Promise((resolve) => {
    const done = () => resolve(new Blob(r.chunks, { type: r.mime }));
    if (!r.recorder || r.recorder.state === 'inactive') return done();
    r.recorder.addEventListener('stop', done, { once: true });
    r.recorder.stop();
  });
}

async function stopListening() {
  const r = rec;
  if (!r) return;
  rec = null; // no new audio from here on
  stopping = true; // a second click must not start a new session mid-stop

  clearInterval(r.timer);
  const blob = await stopFallback(r);
  try {
    r.processor.disconnect();
    r.source.disconnect();
    r.mute.disconnect();
  } catch (e) {
    /* graph already torn down */
  }
  r.media.getTracks().forEach((t) => t.stop());
  await r.ctx.close().catch(() => {});
  setRecording(false);
  setStatus('Transcribing…');

  await (flushing || Promise.resolve()); // keep chunk order
  const parts = r.pending;
  r.pending = [];
  try {
    if (parts.length) {
      await fetch(`/api/stream/${r.id}/audio`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/octet-stream' },
        body: new Blob(parts, { type: 'application/octet-stream' }),
      });
    }
  } catch (e) {
    setStatus(`⚠️ Live transcription dropped: ${e.message}`, true);
  }

  let data = {};
  try {
    data = await postJson(`/api/stream/${r.id}/stop`);
  } catch (e) {
    setStatus(`⚠️ Transcription failed: ${e.message}`, true);
  }

  const text = (data.text || '').trim();
  const finalized = data.final !== false;
  if (text && finalized) {
    // the stream reached a final transcript — use it directly
    renderLive({ ...data, final: true });
    await runTurn(() =>
      fetch('/api/turn', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, stt_ms: data.stt_ms || 0 }),
      }),
    );
    showLive(false);
  } else if (blob.size) {
    // No final (VAD never settled, websocket died, or nothing was heard):
    // the recording itself is the reliable source, and batch STT keeps the
    // learner's words as spoken. Never send an unfinished partial instead.
    showLive(false);
    await sendAudio(blob);
  } else if (text) {
    // no fallback recording exists — a partial beats losing the turn
    renderLive({ ...data, final: true });
    await runTurn(() =>
      fetch('/api/turn', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, stt_ms: data.stt_ms || 0 }),
      }),
    );
    showLive(false);
  } else {
    showLive(false);
    setStatus('⚠️ Could not hear anything — please try again.', true);
  }
  stopping = false;
}

async function toggleMic() {
  if (!started) {
    setStatus('⚠️ Press Start first.', true);
    return;
  }
  if (stopping) return; // the previous recording is still being finalised
  if (rec) return stopListening();
  if (busy) return;
  await startListening();
  els.typed.focus();
}

/* ── end session ────────────────────────────────────────────────────────── */

async function endSession() {
  if (!started) {
    setStatus('⚠️ No active session.', true);
    return;
  }
  setBusy(true);
  setStatus('Writing your summary…');
  try {
    const data = await postJson('/api/summary');
    addMessage('tutor', '**Session ended — your written summary is below.**');
    els.summary.innerHTML = markdown(data.markdown, 1);
    els.summaryCard.hidden = false;
    els.summaryCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
    setStatus('✅ Summary ready.');
  } catch (e) {
    setStatus(`⚠️ Summary failed: ${e.message}`, true);
  } finally {
    setBusy(false);
  }
}

/* ── wiring ─────────────────────────────────────────────────────────────── */

els.start.addEventListener('click', startSession);
els.send.addEventListener('click', sendTyped);
els.typed.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    e.preventDefault();
    sendTyped();
  }
});
els.mic.addEventListener('click', toggleMic);
els.end.addEventListener('click', endSession);

clearChat();
loadMeta();
