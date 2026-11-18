/* Priyanka — live voice agent.
 *
 * No composer, no transcript log: the ear is open the whole session and the
 * mouth answers out loud. The browser does the turn-taking locally — it watches
 * the mic level, feeds 16 kHz PCM to the server's Sarvam stream while the
 * learner talks, and sends the turn once they have been quiet for 2 s.
 *
 *   GET  /api/meta                topics
 *   POST /api/session             → greeting text + spoken greeting WAV
 *   POST /api/turn                one learner turn (text or audio body)
 *   POST /api/summary             written summary
 *   POST /api/stream/start        open a live-transcription stream
 *   POST /api/stream/<id>/audio   raw PCM16 chunks in
 *   POST /api/stream/<id>/stop    final transcript out
 */

const $ = (id) => document.getElementById(id);

const els = {
  topic: $('topic'),
  start: $('start'),
  badge: $('badge'),
  status: $('status'),
  orb: $('orb'),
  capYou: $('capYou'),
  capTutor: $('capTutor'),
  mic: $('mic'),
  micLabel: $('micLabel'),
  end: $('end'),
  player: $('player'),
  metric: $('metric'),
  summaryCard: $('summaryCard'),
  summary: $('summary'),
  senseEar: $('senseEar'),
  senseMouth: $('senseMouth'),
  earState: $('earState'),
  mouthState: $('mouthState'),
};

/* ── tuning ─────────────────────────────────────────────────────────────── */

const STT_RATE = 16000;   // Saaras realtime wants linear16 mono at 16 kHz
const FLUSH_MS = 250;     // how much audio each upload carries
const SILENCE_MS = 2000;  // quiet this long and the turn is hers
const MIN_SPEECH_MS = 350; // shorter than this is a cough, not a sentence
const GATE_BASE = 0.018;  // RMS floor for "someone is talking"
const GATE_SPEAKING = 0.05; // higher while she is talking: that is barge-in
const NOISE_EMA = 0.05;   // room-noise tracker
const SILENCE_WAV = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAgD4AAAB9AAACABAAZGF0YQAAAAA=';

/* The turn-taking rule itself lives in vad.js — DOM-free, and tested in node:
 * quiet for SILENCE_MS after speech ends the utterance. */
const watcher = new TurnWatcher({
  silenceMs: SILENCE_MS,
  minSpeechMs: MIN_SPEECH_MS,
  gateBase: GATE_BASE,
  gateSpeaking: GATE_SPEAKING,
  noiseEma: NOISE_EMA,
});


/* ── state ──────────────────────────────────────────────────────────────── */

let started = false;
let muted = false;
let speaking = false;     // her voice is playing right now
let playing = false;      // the <audio> element is mid-file
let finalizing = false;
let level = 0;
let stateName = 'idle';

const ear = { media: null, ctx: null, source: null, processor: null, sink: null, open: false };
let stream = null;        // the live-transcription stream for the current utterance

let turnChain = Promise.resolve();
const audioQueue = [];
let earError = ''; // the real reason the mic did not open, for the retry hint

/* ── view ───────────────────────────────────────────────────────────────── */

const STATE_TEXT = {
  idle: 'Idle',
  connecting: 'Connecting — she speaks first…',
  listening: 'Ear on — speak whenever you like',
  hearing: 'Hearing you — she takes the turn after 2 s of quiet',
  thinking: 'Thinking…',
  speaking: 'She is speaking — talk over her any time',
  muted: 'Ear off — nothing is being recorded',
  ended: 'Session ended',
};

function setStatus(text, warn = false) {
  els.status.textContent = text;
  els.status.classList.toggle('warn', warn);
}

function setState(name, text, warn = false) {
  stateName = name;
  els.orb.dataset.state = name;
  setStatus(text || STATE_TEXT[name] || '', warn);
  paintSenses();
}

function paintSenses() {
  const earOn = started && !muted;
  const hearing = stateName === 'hearing';
  els.senseEar.classList.toggle('on', earOn && !hearing);
  els.senseEar.classList.toggle('hot', earOn && hearing);
  els.senseEar.classList.toggle('off', !earOn);
  els.earState.textContent = !started ? 'off' : muted ? 'off' : hearing ? 'hearing' : 'on';

  els.senseMouth.classList.toggle('on', speaking);
  els.mouthState.textContent = speaking ? 'speaking' : 'ready';
}

function setCap(which, text) {
  const el = which === 'you' ? els.capYou : els.capTutor;
  const value = (text || '').trim();
  el.textContent = value || '—';
  el.classList.toggle('quiet', !value);
}

function setLevel(rms) {
  const target = Math.min(1, rms * 12);
  level += (target - level) * 0.35;
  els.orb.style.setProperty('--level', level.toFixed(3));
}

function setBadge(data) {
  els.badge.textContent = data.awaiting_confidence
    ? 'Answer the confidence question'
    : `Level ${data.level} · ${data.level_name}`;
}

function showTimings(t) {
  if (!t) return;
  const s = (ms) => (ms / 1000).toFixed(1);
  els.metric.textContent =
    `STT ${s(t.stt)}s · LLM ${s(t.llm)}s · TTS ${s(t.tts)}s · turn ${s(t.total)}s`;
}

/* ── summary markdown (only place text is still rendered) ───────────────── */

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
    if (/^\s+\S/.test(raw) && list && html.endsWith('</li>')) {
      html = `${html.slice(0, -'</li>'.length)} ${inline(line)}</li>`;
      continue;
    }
    let m;
    if ((m = line.match(/^(#{1,6})\s+(.*)$/))) {
      closeList();
      const n = Math.min(m[1].length + bump, 6);
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

/* ── audio plumbing ─────────────────────────────────────────────────────── */

function pickMime() {
  const options = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];
  return options.find((m) => window.MediaRecorder && MediaRecorder.isTypeSupported(m)) || '';
}

/** 16-bit little-endian PCM, resampled to 16 kHz if the context refused it. */
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

function rmsOf(samples) {
  let sum = 0;
  for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
  return Math.sqrt(sum / (samples.length || 1));
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

/* ── the mouth: her voice, queued and interruptible ─────────────────────── */

function pump() {
  if (playing) return;
  const url = audioQueue.shift();
  if (!url) {
    speaking = false;
    if (started) setState(muted ? 'muted' : 'listening');
    else paintSenses();
    return;
  }
  playing = true;
  speaking = true;
  setState('speaking');
  els.player.src = url;
  els.player.play().catch(() => {
    playing = false;
    speaking = false;
    pump();
  });
}

function enqueueAudio(url) {
  if (!url) {
    if (!audioQueue.length && !playing) {
      speaking = false;
      if (started) setState(muted ? 'muted' : 'listening');
    }
    return;
  }
  audioQueue.push(url);
  pump();
}

els.player.addEventListener('ended', () => {
  playing = false;
  if (audioQueue.length) {
    pump();
    return;
  }
  speaking = false;
  if (started) setState(muted ? 'muted' : 'listening');
  else paintSenses();
});

/** The learner talked over her: cut the voice, keep the ear. */
function bargeIn() {
  audioQueue.length = 0;
  playing = false;
  speaking = false;
  try {
    els.player.pause();
    els.player.currentTime = 0;
  } catch (e) {
    /* nothing playing after all */
  }
  setState('hearing');
}

/* ── the ear: one stream per utterance, always the next one open ────────── */

async function openStream() {
  if (stream || !started || muted || !ear.open) return stream;
  let id;
  try {
    ({ id } = await postJson('/api/stream/start'));
  } catch (e) {
    setStatus(`⚠️ Live transcription unavailable: ${e.message}`, true);
    return null;
  }

  const s = { id, pending: [], chunks: [], recorder: null, mime: 'audio/webm', flushing: null, timer: null };

  // Safety net for this utterance only: if the stream yields no words, the
  // recording itself is uploaded and transcribed the batch way.
  try {
    const mime = pickMime();
    s.mime = (mime || 'audio/webm').split(';')[0];
    s.recorder = new MediaRecorder(ear.media, mime ? { mimeType: mime } : undefined);
    s.recorder.ondataavailable = (e) => {
      if (e.data && e.data.size) s.chunks.push(e.data);
    };
    s.recorder.start();
  } catch (e) {
    s.recorder = null;
  }

  s.timer = setInterval(() => flushPending(s), FLUSH_MS);
  stream = s;
  watcher.reset(); // a fresh utterance, a fresh silence clock
  return s;
}

function flushPending(s) {
  if (!s || !s.pending.length) return s && s.flushing;
  const parts = s.pending;
  s.pending = [];
  const body = new Blob(parts, { type: 'application/octet-stream' });

  s.flushing = (s.flushing || Promise.resolve()).then(async () => {
    try {
      const res = await fetch(`/api/stream/${s.id}/audio`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/octet-stream' },
        body,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || `stream ${res.status}`);
      const text = (data.text || '').trim();
      if (text && s === stream) setCap('you', text); // live words while he speaks
    } catch (e) {
      setStatus(`⚠️ Live transcription dropped: ${e.message}`, true);
    }
  });
  return s.flushing;
}

function stopRecorder(s) {
  return new Promise((resolve) => {
    if (!s || !s.recorder || s.recorder.state === 'inactive') {
      resolve(s && s.chunks.length ? new Blob(s.chunks, { type: s.mime }) : null);
      return;
    }
    s.recorder.addEventListener(
      'stop',
      () => resolve(s.chunks.length ? new Blob(s.chunks, { type: s.mime }) : null),
      { once: true },
    );
    s.recorder.stop();
  });
}

/** Close the current utterance: last chunk in, final transcript out. */
async function closeStream() {
  const s = stream;
  if (!s) return { text: '', stt_ms: 0, blob: null };
  stream = null;
  clearInterval(s.timer);

  await (s.flushing || Promise.resolve());
  const parts = s.pending;
  s.pending = [];
  if (parts.length) {
    try {
      await fetch(`/api/stream/${s.id}/audio`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/octet-stream' },
        body: new Blob(parts, { type: 'application/octet-stream' }),
      });
    } catch (e) {
      setStatus(`⚠️ Live transcription dropped: ${e.message}`, true);
    }
  }

  const blob = await stopRecorder(s);
  let data = {};
  try {
    data = await postJson(`/api/stream/${s.id}/stop`);
  } catch (e) {
    setStatus(`⚠️ Transcription failed: ${e.message}`, true);
  }
  return { text: (data.text || '').trim(), stt_ms: data.stt_ms || 0, blob };
}

async function startEar() {
  if (ear.open) return true;
  let media;
  try {
    media = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true, // her own voice must not reopen the turn
        noiseSuppression: true,
        autoGainControl: true,
        channelCount: 1,
      },
    });
  } catch (e) {
    earError = e.message;
    setState('idle', `⚠️ Microphone unavailable: ${e.message}`, true);
    return false;
  }

  let ctx;
  try {
    ctx = new AudioContext({ sampleRate: STT_RATE });
  } catch (e) {
    ctx = new AudioContext(); // older browsers: toPcm16 resamples
  }
  await ctx.resume().catch(() => {});

  const source = ctx.createMediaStreamSource(media);
  const processor = ctx.createScriptProcessor(4096, 1, 1);
  const sink = ctx.createGain();
  sink.gain.value = 0; // keeps the graph alive without echoing the mic
  processor.onaudioprocess = (e) => onBlock(e.inputBuffer.getChannelData(0), ctx.sampleRate);
  source.connect(processor);
  processor.connect(sink);
  sink.connect(ctx.destination);

  Object.assign(ear, { media, ctx, source, processor, sink, open: true });
  watcher.reset();
  await openStream();
  return true;
}

async function stopEar() {
  await closeStream();
  if (ear.processor) {
    ear.processor.onaudioprocess = null;
    try { ear.processor.disconnect(); } catch (e) { /* torn down */ }
  }
  if (ear.source) try { ear.source.disconnect(); } catch (e) { /* torn down */ }
  if (ear.sink) try { ear.sink.disconnect(); } catch (e) { /* torn down */ }
  if (ear.media) ear.media.getTracks().forEach((t) => t.stop());
  if (ear.ctx) await ear.ctx.close().catch(() => {});
  ear.media = ear.ctx = ear.source = ear.processor = ear.sink = null;
  ear.open = false;
  level = 0;
  els.orb.style.setProperty('--level', '0');
}

/* ── turn taking ────────────────────────────────────────────────────────── */

function onBlock(samples, rate) {
  const rms = rmsOf(samples);
  setLevel(rms);
  if (!started || muted || !stream) return;

  const blockMs = (samples.length / rate) * 1000;
  const event = watcher.push(rms, blockMs, performance.now(), speaking || playing);

  if (event === 'speech-start') {
    // she stops mid-sentence, the ear stays open
    if (speaking || playing) bargeIn();
    else setState('hearing');
  }

  stream.pending.push(toPcm16(samples, rate));

  if (event === 'turn-end') finalizeUtterance();
}

async function finalizeUtterance() {
  if (finalizing) return;
  finalizing = true;
  try {
    const { text, stt_ms, blob } = await closeStream();
    if (started && !muted) openStream(); // the ear is never closed for long
    if (text) {
      setCap('you', text);
      queueTurn(() => runTurn({ text, stt_ms: stt_ms || 0 }));
    } else if (blob && blob.size) {
      queueTurn(() => runTurn({ blob }));
    } else {
      setState('listening', 'Nothing heard — go ahead whenever you are ready');
    }
  } finally {
    finalizing = false;
  }
}

function queueTurn(worker) {
  turnChain = turnChain.then(async () => {
    try {
      await worker();
    } catch (e) {
      setState('listening', `⚠️ ${e.message}`, true);
    }
  });
  return turnChain;
}

async function runTurn({ text, stt_ms, blob }) {
  setState('thinking');
  let data;
  if (blob) {
    const res = await fetch('/api/turn', {
      method: 'POST',
      headers: { 'Content-Type': blob.type || 'audio/webm' },
      body: blob,
    });
    data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Turn failed (${res.status})`);
  } else {
    data = await postJson('/api/turn', { text, stt_ms: stt_ms || 0 });
  }

  if (data.heard) setCap('you', data.heard);
  setCap('tutor', data.reply2 ? `${data.reply} ${data.reply2}` : data.reply);
  setBadge(data);
  showTimings(data.timings);
  reportWarning(data);
  enqueueAudio(data.audio);
  if (data.audio2) audioQueue.push(data.audio2); // question after the correction
  if (!data.audio) setState('listening');
}

function reportWarning(data) {
  if (data.warning) setStatus(`⚠️ ${data.warning}`, true);
}

/* ── session ────────────────────────────────────────────────────────────── */

function unlockAudio() {
  // A press is the only gesture we get; spend it so her first sentence (queued
  // seconds later) is not blocked by the autoplay policy.
  try {
    els.player.src = SILENCE_WAV;
    els.player.play().catch(() => {});
  } catch (e) {
    /* nothing to unlock */
  }
}

async function loadMeta() {
  try {
    const res = await fetch('/api/meta');
    if (!res.ok) throw new Error(`meta ${res.status}`);
    const meta = await res.json();
    // topics come from the server's own TOPICS list and are escaped here, so
    // the option markup cannot carry a tag
    els.topic.innerHTML = meta.topics
      .map((t) => `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`)
      .join('');
  } catch (e) {
    setStatus(`⚠️ Could not load topics: ${e.message}`, true);
  }
}

async function startSession() {
  unlockAudio();
  els.start.disabled = true;
  els.summaryCard.hidden = true;
  els.summary.innerHTML = '';
  els.metric.textContent = '';
  audioQueue.length = 0;
  setState('connecting');

  try {
    const data = await postJson('/api/session', { topic: els.topic.value });
    started = true;
    muted = false;
    els.topic.disabled = true;
    els.mic.disabled = false;
    els.end.disabled = false;
    els.mic.setAttribute('aria-pressed', 'true');
    els.micLabel.textContent = 'Mute ear';
    setBadge(data);
    setCap('tutor', data.greeting);
    setCap('you', '');

    const open = await startEar();
    if (!open) {
      // no ear, no session: put the page back the way it was
      started = false;
      muted = true;
      els.start.disabled = false;
      els.topic.disabled = false;
      els.mic.disabled = true;
      els.end.disabled = true;
      els.mic.setAttribute('aria-pressed', 'true');
      els.micLabel.textContent = 'Mute ear';
      setState('idle', `⚠️ Microphone unavailable: ${earError} — press Start to retry`, true);
      return;
    }
    earError = '';
    paintSenses();
    setState('speaking');
    enqueueAudio(data.audio); // her first line, out loud
    if (data.warning) setStatus(`⚠️ ${data.warning}`, true);
    else if (!data.audio) setState('listening', '⚠️ The greeting came back silent', true);
  } catch (e) {
    els.start.disabled = false;
    setState('idle', `⚠️ ${e.message}`, true);
  }
}

async function toggleEar() {
  if (!started) return;
  muted = !muted;
  els.mic.setAttribute('aria-pressed', String(!muted));
  els.micLabel.textContent = muted ? 'Unmute ear' : 'Mute ear';

  if (muted) {
    watcher.reset();
    if (playing || audioQueue.length) {
      audioQueue.length = 0;
      playing = false;
      speaking = false;
      try { els.player.pause(); } catch (e) { /* not playing */ }
    }
    await stopEar(); // track stopped: the OS mic indicator goes out
    setState('muted');
  } else {
    const open = await startEar();
    if (open) setState('listening');
  }
}

async function endSession() {
  if (!started) return;
  els.end.disabled = true;
  els.mic.disabled = true;
  setState('thinking', 'Writing your summary…');
  try {
    audioQueue.length = 0;
    playing = false;
    speaking = false;
    try { els.player.pause(); } catch (e) { /* not playing */ }
    muted = true;
    await stopEar();
    const data = await postJson('/api/summary');
    // markdown() escapes every line before it builds tags, so model output
    // cannot inject markup here
    els.summary.innerHTML = markdown(data.markdown, 1);
    els.summaryCard.hidden = false;
    els.summaryCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
    started = false;
    els.start.disabled = false;
    els.topic.disabled = false;
    els.mic.setAttribute('aria-pressed', 'true');
    els.micLabel.textContent = 'Mute ear';
    setState('ended');
  } catch (e) {
    els.end.disabled = false;
    els.mic.disabled = false;
    setState('listening', `⚠️ Summary failed: ${e.message}`, true);
  }
}

/* ── wiring ─────────────────────────────────────────────────────────────── */

els.start.addEventListener('click', startSession);
els.mic.addEventListener('click', toggleEar);
els.end.addEventListener('click', endSession);

loadMeta();
setState('idle', 'Press Start — her ear opens and she speaks first');
