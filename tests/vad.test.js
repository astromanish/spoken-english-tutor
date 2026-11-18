/* The turn-taking rule, exercised without a microphone:
 *   node --test tests/
 * Values are real measurements — 0.09 RMS is Bulbul speech, 0.0023 a quiet
 * room, 0.0 digital silence.
 */
const test = require('node:test');
const assert = require('node:assert');
const { TurnWatcher, DEFAULTS } = require('../static/vad.js');

const BLOCK = 256; // ms per mic block
const SPEECH = 0.09;
const HISS = 0.0023;
const SILENCE = 0.0;

/** Feed `ms` of a level in 256 ms blocks; returns the events with timestamps. */
function feed(w, rms, ms, t, speaking = false) {
  const events = [];
  for (let elapsed = 0; elapsed < ms; elapsed += BLOCK) {
    const ev = w.push(rms, BLOCK, t, speaking);
    if (ev) events.push({ ev, t });
    t += BLOCK;
  }
  return { events, t };
}

test('two seconds of quiet ends the turn', () => {
  const w = new TurnWatcher();
  let t = 0;
  let r = feed(w, SPEECH, 1024, t);
  assert.deepStrictEqual(r.events.map((e) => e.ev), ['speech-start']);
  const speechEnd = r.t;
  const turn = r.events[0].t;

  // 1.75 s of quiet — still his turn
  r = feed(w, SILENCE, 1750, r.t);
  assert.deepStrictEqual(r.events, []);

  // crossing 2 s of quiet — hers now
  r = feed(w, SILENCE, 512, r.t);
  assert.strictEqual(r.events.length, 1);
  assert.strictEqual(r.events[0].ev, 'turn-end');
  const quietFor = r.events[0].t - speechEnd;
  assert.ok(quietFor >= 2000 && quietFor < 2256, `quiet for ${quietFor} ms`);
  assert.ok(speechEnd - turn >= 768, 'speech was long enough to count');
});

test('a cough shorter than 350 ms never becomes a turn', () => {
  const w = new TurnWatcher();
  let t = 0;
  let r = feed(w, SPEECH, 256, t); // one block only
  assert.deepStrictEqual(r.events.map((e) => e.ev), ['speech-start']);
  r = feed(w, SILENCE, 4000, r.t);
  assert.deepStrictEqual(r.events, [], 'no turn-end for 256 ms of voice');
});

test('a quiet room never opens a turn', () => {
  const w = new TurnWatcher();
  const r = feed(w, HISS, 20000, 0);
  assert.deepStrictEqual(r.events, []);
});

test('speaking again resets the silence clock', () => {
  const w = new TurnWatcher();
  let t = 0;
  const a = feed(w, SPEECH, 512, t);
  t = a.t;
  const b = feed(w, SILENCE, 1500, t); // pause, but under 2 s
  t = b.t;
  const c = feed(w, SPEECH, 512, t); // he carries on mid-sentence
  t = c.t;
  const d = feed(w, SILENCE, 1750, t); // the final pause, still short
  assert.deepStrictEqual([...b.events, ...c.events, ...d.events], []);

  const e = feed(w, SILENCE, 512, d.t);
  assert.strictEqual(e.events.length, 1);
  assert.strictEqual(e.events[0].ev, 'turn-end');
});

test('her own voice is filtered while she is speaking', () => {
  // While she talks the gate is 0.05: residual echo of her voice at 0.03 is
  // not speech, but the learner talking at 0.09 is.
  const w = new TurnWatcher();
  let r = feed(w, 0.03, 4000, 0, true);
  assert.deepStrictEqual(r.events, [], 'echo does not barge in');
  r = feed(w, 0.09, 512, r.t, true);
  assert.deepStrictEqual(r.events.map((e) => e.ev), ['speech-start'], 'the learner does');
});

test('reset clears a turn in progress', () => {
  const w = new TurnWatcher();
  let r = feed(w, SPEECH, 512, 0);
  assert.strictEqual(r.events.length, 1);
  w.reset();
  r = feed(w, SILENCE, 4000, r.t);
  assert.deepStrictEqual(r.events, []);
  assert.strictEqual(DEFAULTS.silenceMs, 2000);
});
