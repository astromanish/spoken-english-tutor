/* A WAV wrapper for the PCM the browser already captured — DOM-free, tested.
 *
 * The batch fallback (the live stream came back empty) used to upload a webm
 * from MediaRecorder, which only a host with ffmpeg could convert. We already
 * hold every 16 kHz mono PCM16 block, so wrapping them in a 44-byte RIFF header
 * gives Saaras a file it reads natively — no ffmpeg, no MediaRecorder.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.Wav = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  const HEADER_BYTES = 44;

  /**
   * @param {Uint8Array[]} blocks PCM16 little-endian, mono, at `sampleRate`
   * @param {number} sampleRate defaults to 16000 (what Saaras expects)
   * @returns {{bytes: Uint8Array, header: number, dataBytes: number}}
   */
  function wavBytes(blocks, sampleRate = 16000) {
    const dataBytes = blocks.reduce((n, b) => n + b.byteLength, 0);
    const out = new Uint8Array(HEADER_BYTES + dataBytes);
    const view = new DataView(out.buffer);
    const ascii = (offset, str) => {
      for (let i = 0; i < str.length; i++) out[offset + i] = str.charCodeAt(i);
    };

    ascii(0, 'RIFF');
    view.setUint32(4, 36 + dataBytes, true); // everything after this field
    ascii(8, 'WAVE');
    ascii(12, 'fmt ');
    view.setUint32(16, 16, true); // PCM chunk size
    view.setUint16(20, 1, true); // format 1 = PCM
    view.setUint16(22, 1, true); // mono
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true); // byte rate: rate * channels * 2
    view.setUint16(32, 2, true); // block align
    view.setUint16(34, 16, true); // bits per sample
    ascii(36, 'data');
    view.setUint32(40, dataBytes, true);

    let at = HEADER_BYTES;
    for (const block of blocks) {
      out.set(block instanceof Uint8Array ? block : new Uint8Array(block), at);
      at += block.byteLength;
    }
    return { bytes: out, header: HEADER_BYTES, dataBytes };
  }

  return { wavBytes, HEADER_BYTES };
});
