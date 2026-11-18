/* Priyanka — live voice agent.
 *
 * No composer, no transcript log: the ear is open the whole session and the
 * mouth answers out loud. The browser does the turn-taking locally — it watches
 * the mic level, feeds 16 kHz PCM to the server's Sarvam stream while the
 * learner talks, and sends the turn once they have been quiet for 0.5 s.
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
  voice: $('voice'),
  preview: $('preview'),
  start: $('start'),
  badge: $('badge'),
  status: $('status'),
  orb: $('orb'),
  capYou: $('capYou'),
  capTutor: $('capTutor'),
  mic: $('mic'),
  end: $('end'),
  metric: $('metric'),
  summaryCard: $('summaryCard'),
  summary: $('summary'),
  statePill: $('statePill'),
  stateLabel: $('stateLabel'),
};

/* ── tuning ─────────────────────────────────────────────────────────────── */

const STT_RATE = 16000;   // Saaras realtime wants linear16 mono at 16 kHz
const FLUSH_MS = 250;     // how much audio each upload carries
const SILENCE_MS = 500;   // quiet this long and the turn is hers
const MIN_SPEECH_MS = 350; // shorter than this is a cough, not a sentence
const GATE_BASE = 0.018;  // RMS floor for "someone is talking"
const GATE_SPEAKING = 0.05; // higher while she is talking: that is barge-in
const NOISE_EMA = 0.05;   // room-noise tracker

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

/* Continuation and barge-in bookkeeping lives in turns.js (DOM-free, tested):
   a reply that lands while he is still talking is held, his fragment is
   carried forward, and the next utterance is sent as one merged turn. */
const turns = new TurnCoordinator();
let heldReply = null; // { token, data } — received, not played

/* ── view ───────────────────────────────────────────────────────────────── */

const STATE_TEXT = {
  idle: '',
  connecting: 'Connecting — she speaks first…',
  listening: 'Mic on — speak whenever you like',
  hearing: 'Hearing you — she takes the turn after half a second of quiet',
  thinking: 'Thinking…',
  speaking: 'She is speaking — talk over her any time',
  muted: 'Mic off — nothing is being recorded',
  ended: 'Session ended',
};

/** aria-pressed is the truth for the mic icon: true = muted (crossed mic). */
function setMicPressed(isMuted) {
  els.mic.setAttribute('aria-pressed', String(!isMuted));
  const label = isMuted ? 'Unmute microphone' : 'Mute microphone';
  els.mic.setAttribute('aria-label', label);
  els.mic.title = label;
}

function setStatus(text, warn = false) {
  els.status.textContent = text;
  els.status.classList.toggle('warn', warn);
}

function setState(name, text, warn = false) {
  stateName = name;
  els.orb.dataset.state = name;
  setStatus(text || STATE_TEXT[name] || '', warn);
  paintState();
}

/* The stage stays quiet at rest: the pill appears only for a state that is
   happening right now (listening, hearing, thinking, speaking). */
const PILL = {
  listening: 'Listening',
  hearing: 'Listening to you',
  thinking: 'Thinking',
  speaking: 'Speaking',
};

function paintState() {
  const label = PILL[stateName];
  els.statePill.hidden = !label;
  if (!label) return;
  els.statePill.dataset.state = stateName;
  els.stateLabel.textContent = label;
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

/** The utterance as a WAV (see wav.js) — Saaras reads it without ffmpeg. */
function utteranceBlob(s) {
  if (!s || !s.pcm.length) return null;
  // toPcm16 already resampled every block to STT_RATE, so the header says 16 kHz
  const { bytes } = Wav.wavBytes(s.pcm, STT_RATE);
  return new Blob([bytes], { type: 'audio/wav' });
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

/* ── the mouth: her voice, streamed and interruptible ───────────────────────
 *
 * /speak returns raw linear16 PCM chunked straight from Bulbul, so the first
 * 30-60 ms of sound arrives ~0.4 s after the turn instead of after a finished
 * file. Each chunk becomes an AudioBuffer scheduled hard against the previous
 * one, which is gapless by construction, needs no codec, and makes barge-in a
 * matter of stopping the sources that are queued in the graph.
 */

const playback = {
  ctx: null,
  cursor: 0,      // when the next buffer should start
  sources: [],    // scheduled but not finished — the barge-in kill list
  abort: null,    // cancels the fetch that is feeding the scheduler
};

function playbackContext() {
  if (!playback.ctx) {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    playback.ctx = new Ctx();
  }
  playback.ctx.resume().catch(() => {});
  return playback.ctx;
}

function stopPlayback() {
  if (playback.abort) {
    try { playback.abort.abort(); } catch (e) { /* already done */ }
    playback.abort = null;
  }
  for (const src of playback.sources) {
    try { src.stop(); } catch (e) { /* already stopped */ }
  }
  playback.sources = [];
  if (playback.ctx) playback.cursor = playback.ctx.currentTime;
}

function schedule(samples, rate, when) {
  const ctx = playbackContext();
  const buffer = ctx.createBuffer(1, samples.length, rate);
  buffer.copyToChannel(samples, 0);
  const src = ctx.createBufferSource();
  src.buffer = buffer;
  src.connect(ctx.destination);
  const at = Math.max(when, ctx.currentTime + 0.02);
  src.start(at);
  playback.sources.push(src);
  src.onended = () => {
    playback.sources = playback.sources.filter((s) => s !== src);
  };
  return at + buffer.duration;
}

/** A whole file (the REST fallback) still goes through the same scheduler. */
async function playFile(blob) {
  const ctx = playbackContext();
  const decoded = await ctx.decodeAudioData(await blob.arrayBuffer());
  const samples = decoded.getChannelData(0);
  playback.cursor = Math.max(playback.cursor, ctx.currentTime + 0.06);
  playback.cursor = schedule(samples, decoded.sampleRate, playback.cursor);
  await new Promise((r) => setTimeout(r, Math.max(0, (playback.cursor - ctx.currentTime) * 1000) + 60));
}

/** Stream one message into the audio graph and resolve when it has been heard. */
async function playStream(url) {
  const ctx = playbackContext();
  playback.abort = new AbortController();
  const res = await fetch(url, { signal: playback.abort.signal });
  if (!res.ok) throw new Error(`audio ${res.status}`);

  if ((res.headers.get('Content-Type') || '').startsWith('audio/wav')) {
    return playFile(await res.blob());        // REST fallback
  }

  const rate = Number(res.headers.get('X-Sample-Rate') || STT_RATE);
  const reader = res.body.getReader();
  let carry = new Uint8Array(0);
  playback.cursor = Math.max(playback.cursor, ctx.currentTime + 0.06);

  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    let bytes = value;
    if (carry.length) {                       // stitch a sample split across reads
      const joined = new Uint8Array(carry.length + bytes.length);
      joined.set(carry); joined.set(bytes, carry.length);
      bytes = joined; carry = new Uint8Array(0);
    }
    if (bytes.length & 1) {
      carry = bytes.slice(-1);
      bytes = bytes.slice(0, -1);
    }
    if (!bytes.length) continue;

    const pcm = new Int16Array(bytes.buffer, bytes.byteOffset, bytes.length >> 1);
    const samples = new Float32Array(pcm.length);
    for (let i = 0; i < pcm.length; i++) samples[i] = pcm[i] / 32768;
    playback.cursor = schedule(samples, rate, playback.cursor);
  }

  const left = Math.max(0, (playback.cursor - ctx.currentTime) * 1000);
  await new Promise((r) => setTimeout(r, left + 60));
}

async function pump() {
  if (playing) return;
  const url = audioQueue.shift();
  if (!url) {
    speaking = false;
    if (stateName === 'hearing') return paintState(); // he is mid-sentence
    if (started) setState(muted ? 'muted' : 'listening');
    else paintState();
    return;
  }
  playing = true;
  speaking = true;
  setState('speaking');
  try {
    await playStream(url);
  } catch (e) {
    if (e.name !== 'AbortError') setStatus(`⚠️ ${e.message}`, true);
  }
  playing = false;
  if (audioQueue.length) return pump();
  speaking = false;
  if (stateName === 'hearing') return paintState();
  if (started) setState(muted ? 'muted' : 'listening');
  else paintState();
}

function enqueueAudio(url) {
  if (!url) {
    if (!audioQueue.length && !playing && stateName !== 'hearing') {
      speaking = false;
      if (started) setState(muted ? 'muted' : 'listening');
    }
    return;
  }
  audioQueue.push(url);
  pump();
}

/** The learner talked over her: cut the voice, keep the ear. */
function bargeIn() {
  audioQueue.length = 0;
  playing = false;
  speaking = false;
  stopPlayback();
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

  // `pending` is what goes up the wire; `pcm` is the same audio kept locally as
  // the safety net for this utterance, in case the stream comes back empty.
  const s = { id, pending: [], pcm: [], flushing: null, timer: null };

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

  const blob = utteranceBlob(s);
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
    const action = turns.onSpeechStart(stateName);
    if (action === 'barge') {
      bargeIn(); // she stops mid-sentence, the ear stays open
    } else if (action === 'supersede') {
      // she had not started answering yet: whatever he said before was half a
      // sentence, so her reply is held and his words carry into the next turn
      setStatus('You kept going — she will answer the whole sentence');
    }
    setState('hearing');
  }

  const pcm = toPcm16(samples, rate);
  stream.pending.push(pcm);
  stream.pcm.push(pcm);

  if (event === 'turn-end') finalizeUtterance();
}

async function finalizeUtterance() {
  if (finalizing) return;
  finalizing = true;
  try {
    const { text, stt_ms, blob } = await closeStream();
    if (started && !muted) openStream(); // the ear is never closed for long

    const step = turns.onUtterance(text);
    if (step && step.restore !== undefined) {
      // the "continuation" was a cough: play the answer that was held back
      setCap('you', '');
      playHeld(step.restore);
      return;
    }
    if (step) {
      setCap('you', step.text);
      if (step.replace) setStatus('Whole sentence sent — answering that, not the fragment');
      queueTurn(() => runTurn({
        text: step.text, stt_ms: stt_ms || 0, token: step.token, replace: step.replace,
      }));
    } else if (blob && blob.size) {
      // audio-only fallback: the words are the server's to find, so no merging
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

async function runTurn({ text, stt_ms, blob, token, replace }) {
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
    data = await postJson('/api/turn', {
      text,
      stt_ms: stt_ms || 0,
      replace_previous: Boolean(replace),
    });
  }

  const verdict = token ? turns.onReply(token) : 'play';
  if (verdict === 'hold') {
    // he is still talking: keep the answer, do not speak over him
    heldReply = { token, data };
    return;
  }
  showReply(data);
}

/** Her answer, out loud: captions, level, timings, then the audio queue. */
function showReply(data) {
  if (data.heard) setCap('you', data.heard);
  setCap('tutor', data.reply2 ? `${data.reply} ${data.reply2}` : data.reply);
  setBadge(data);
  showTimings(data.timings);
  reportWarning(data);
  enqueueAudio(data.audio);
  if (data.audio2) audioQueue.push(data.audio2); // question after the correction
  if (!data.audio) setState('listening');
}

/** Nothing was actually said after all — she gets her held answer now. */
function playHeld(token) {
  if (!heldReply || heldReply.token !== token) return;
  const { data } = heldReply;
  heldReply = null;
  turns.settle(token);
  showReply(data);
}

function reportWarning(data) {
  if (data.warning) setStatus(`⚠️ ${data.warning}`, true);
}

/* ── session ────────────────────────────────────────────────────────────── */

function unlockAudio() {
  // A press is the only gesture we get; spend it resuming the audio graph so her
  // first sentence (queued milliseconds later) is not blocked by autoplay rules.
  try { playbackContext().resume(); } catch (e) { /* nothing to unlock */ }
}

const VOICE_KEY = 'priyanka.voice';

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

    // Five voices, described by character — not by speaker name: the tutor is
    // Priyanka, so the picker chooses how she sounds, not who she is.
    els.voice.innerHTML = (meta.speakers || [])
      .map((sp) => {
        const label = sp.label || sp.id;
        return `<option value="${escapeHtml(sp.id)}">${escapeHtml(label)}</option>`;
      })
      .join('');

    let saved = '';
    try { saved = localStorage.getItem(VOICE_KEY) || ''; } catch (e) { /* private mode */ }
    const known = (meta.speakers || []).some((sp) => sp.id === saved);
    els.voice.value = known ? saved : meta.default_speaker;
    els.preview.disabled = !els.voice.value;
  } catch (e) {
    setStatus(`⚠️ Could not load the setup: ${e.message}`, true);
  }
}

/** Speak a two-line sample in the chosen voice, before committing to a session. */
async function previewVoice() {
  const speaker = els.voice.value;
  if (!speaker) return;
  const label = els.preview.textContent;
  els.preview.disabled = true;
  els.preview.textContent = 'Loading…';
  try {
    const data = await postJson('/api/preview', { speaker });
    if (data.audio) {
      stopPlayback();
      playback.cursor = 0;
      const chosen = els.voice.selectedOptions[0];
      setStatus(`Sample playing · ${chosen ? chosen.text : data.speaker}`);
      await playStream(data.audio);
      setStatus('Ear and mouth ready');
    }
  } catch (e) {
    setStatus(`⚠️ Preview failed: ${e.message}`, true);
  } finally {
    els.preview.disabled = false;
    els.preview.textContent = label;
  }
}

async function startSession() {
  unlockAudio();
  els.start.disabled = true;
  els.summaryCard.hidden = true;
  els.summary.innerHTML = '';
  els.metric.textContent = '';
  audioQueue.length = 0;
  turns.reset();
  heldReply = null;
  setState('connecting');

  try {
    const data = await postJson('/api/session', {
      topic: els.topic.value,
      speaker: els.voice.value,
    });
    started = true;
    muted = false;
    els.topic.disabled = true;
    els.voice.disabled = true;
    els.preview.disabled = true;
    els.mic.disabled = false;
    els.end.disabled = false;
    setMicPressed(false);
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
      els.voice.disabled = false;
      els.preview.disabled = false;
      els.mic.disabled = true;
      els.end.disabled = true;
      setMicPressed(false);
      setState('idle', `⚠️ Microphone unavailable: ${earError} — press Start to retry`, true);
      return;
    }
    earError = '';
    paintState();
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
  setMicPressed(muted);

  if (muted) {
    watcher.reset();
    // Muting closes the ear and nothing else. Her sentence is not the microphone:
    // killing the queue here made "mute me" feel like "stop the lesson", and the
    // learner loses the correction he was being given.
    await stopEar(); // track stopped: the OS mic indicator goes out
    if (playing || speaking) paintState();   // she is still talking; say so
    else setState('muted');
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
    stopPlayback();
    muted = true;
    turns.reset();
    heldReply = null;
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
    els.voice.disabled = false;
    els.preview.disabled = false;
    setMicPressed(false);
    setState('ended');
  } catch (e) {
    els.end.disabled = false;
    els.mic.disabled = false;
    setState('listening', `⚠️ Summary failed: ${e.message}`, true);
  }
}

/* ── wiring ─────────────────────────────────────────────────────────────── */

els.start.addEventListener('click', startSession);
els.preview.addEventListener('click', previewVoice);
els.voice.addEventListener('change', () => {
  try { localStorage.setItem(VOICE_KEY, els.voice.value); } catch (e) { /* private mode */ }
});
els.mic.addEventListener('click', toggleEar);
els.end.addEventListener('click', endSession);

loadMeta();
setState('idle');   // the stage starts quiet: no instruction to read
