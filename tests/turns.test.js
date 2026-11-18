/* Turn coordination, no browser needed:  node --test
 * Covers the two failures the always-on loop has to survive — her reply landing
 * on top of a sentence already in progress, and a 2 s think splitting one
 * sentence into two turns.
 */
const test = require('node:test');
const assert = require('node:assert');
const { TurnCoordinator } = require('../static/turns.js');

test('an uninterrupted turn is sent as-is and played', () => {
  const c = new TurnCoordinator();
  const t = c.begin('I am working in company from two years.');
  assert.deepStrictEqual({ text: t.text, replace: t.replace }, {
    text: 'I am working in company from two years.',
    replace: false,
  });
  assert.strictEqual(c.onReply(t.token), 'play');
  assert.strictEqual(c.carry, '');
  assert.strictEqual(c.inflight, null);
});

test('speech during thinking holds her reply and merges the fragments', () => {
  const c = new TurnCoordinator();
  const first = c.begin('Yesterday I go to office');

  // he was not finished: the reply must not be spoken over him
  assert.strictEqual(c.onSpeechStart('thinking'), 'supersede');
  assert.strictEqual(c.onReply(first.token), 'hold');
  assert.strictEqual(c.carry, 'Yesterday I go to office');

  // he finishes the sentence; the turn goes out as one merged message and
  // replaces the fragment already in her history
  const merged = c.onUtterance('and I am explain everything to my manager.');
  assert.strictEqual(
    merged.text,
    'Yesterday I go to office and I am explain everything to my manager.',
  );
  assert.strictEqual(merged.replace, true);
  assert.strictEqual(c.onReply(merged.token), 'play');
  assert.strictEqual(c.carry, '', 'carry is consumed by the merged turn');
});

test('a continuation that turns out to be a cough restores her reply', () => {
  const c = new TurnCoordinator();
  const first = c.begin('She do not know nothing');
  assert.strictEqual(c.onSpeechStart('thinking'), 'supersede');
  assert.strictEqual(c.onReply(first.token), 'hold');

  // 350 ms of noise, no words: nothing to merge, so the held answer must play
  const result = c.onUtterance('');
  assert.deepStrictEqual(result, { restore: first.token });
  assert.strictEqual(c.carry, '', 'the fragment is not carried forever');
});

test('talking over her while she speaks is a barge-in, not a merge', () => {
  const c = new TurnCoordinator();
  const t = c.begin('I want to meet the doctor');
  assert.strictEqual(c.onReply(t.token), 'play'); // she is speaking now

  assert.strictEqual(c.onSpeechStart('speaking'), 'barge');
  assert.strictEqual(c.carry, '', 'he heard her answer — his next words stand alone');

  const next = c.onUtterance('When did the fever start?');
  assert.strictEqual(next.text, 'When did the fever start?');
  assert.strictEqual(next.replace, false);
});

test('a second interruption carries the merged text, not just the last fragment', () => {
  const c = new TurnCoordinator();
  const a = c.begin('I go to office');
  c.onSpeechStart('thinking');
  c.onReply(a.token);

  const merged = c.onUtterance('every day by bus');
  c.onSpeechStart('thinking'); // interrupted again, before hearing anything
  assert.strictEqual(c.carry, 'I go to office every day by bus');

  const again = c.onUtterance('and it take forty minutes');
  assert.strictEqual(again.text, 'I go to office every day by bus and it take forty minutes');
  assert.strictEqual(again.replace, true);
});

test('speech while listening (no turn in flight) does nothing special', () => {
  const c = new TurnCoordinator();
  assert.strictEqual(c.onSpeechStart('listening'), 'none');
  assert.strictEqual(c.carry, '');
});

test('reset clears a half-finished merge', () => {
  const c = new TurnCoordinator();
  const a = c.begin('some fragment');
  c.onSpeechStart('thinking');
  c.onReply(a.token);
  c.reset();
  assert.strictEqual(c.carry, '');
  assert.strictEqual(c.held, null);
  assert.strictEqual(c.inflight, null);
});
