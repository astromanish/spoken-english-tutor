/* The fallback WAV, checked byte by byte:  node --test */
const test = require('node:test');
const assert = require('node:assert');
const { wavBytes, HEADER_BYTES } = require('../static/wav.js');

const ascii = (bytes, at, len) => String.fromCharCode(...bytes.slice(at, at + len));
const u32 = (bytes, at) => new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength).getUint32(at, true);
const u16 = (bytes, at) => new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength).getUint16(at, true);

test('header is a valid 16 kHz mono PCM16 RIFF', () => {
  const pcm = new Uint8Array(3200); // 100 ms of silence
  const { bytes, dataBytes } = wavBytes([pcm]);

  assert.strictEqual(bytes.length, HEADER_BYTES + 3200);
  assert.strictEqual(ascii(bytes, 0, 4), 'RIFF');
  assert.strictEqual(ascii(bytes, 8, 4), 'WAVE');
  assert.strictEqual(ascii(bytes, 12, 4), 'fmt ');
  assert.strictEqual(ascii(bytes, 36, 4), 'data');

  assert.strictEqual(u32(bytes, 4), 36 + 3200, 'RIFF size counts everything after it');
  assert.strictEqual(u32(bytes, 16), 16, 'fmt chunk size');
  assert.strictEqual(u16(bytes, 20), 1, 'format = PCM');
  assert.strictEqual(u16(bytes, 22), 1, 'mono');
  assert.strictEqual(u32(bytes, 24), 16000, 'sample rate');
  assert.strictEqual(u32(bytes, 28), 32000, 'byte rate');
  assert.strictEqual(u16(bytes, 32), 2, 'block align');
  assert.strictEqual(u16(bytes, 34), 16, 'bits per sample');
  assert.strictEqual(u32(bytes, 40), dataBytes, 'data chunk size');
});

test('PCM blocks land after the header, in order, unmodified', () => {
  const a = new Uint8Array([1, 2, 3, 4]);
  const b = new Uint8Array([5, 6]);
  const { bytes } = wavBytes([a, b], 16000);

  assert.deepStrictEqual([...bytes.slice(HEADER_BYTES, HEADER_BYTES + 6)], [1, 2, 3, 4, 5, 6]);
  assert.strictEqual(u32(bytes, 40), 6);
});

test('an empty capture still produces a readable, empty WAV', () => {
  const { bytes, dataBytes } = wavBytes([]);
  assert.strictEqual(bytes.length, HEADER_BYTES);
  assert.strictEqual(dataBytes, 0);
  assert.strictEqual(u32(bytes, 4), 36);
  assert.strictEqual(ascii(bytes, 0, 4), 'RIFF');
});

test('a longer context keeps its own sample rate in the header', () => {
  const { bytes } = wavBytes([new Uint8Array(100)], 48000);
  assert.strictEqual(u32(bytes, 24), 48000);
  assert.strictEqual(u32(bytes, 28), 96000);
});
