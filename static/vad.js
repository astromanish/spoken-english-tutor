/* Turn-taking for the live voice agent — DOM-free so it can be tested in node.
 *
 * The browser feeds it one RMS value per ~256 ms mic block; it answers with an
 * event: "speech-start" (the learner began talking — barge-in point) or
 * "turn-end" (they have been quiet for `silenceMs`, so the turn is the
 * tutor's). Everything else is room noise.
 *
 * Calibrated against Bulbul output: normal speech measures ~0.09 RMS, a quiet
 * room ~0.002, digital silence 0.0 — so the base gate sits at 0.018 and the
 * barge-in gate higher still, because while she is speaking the mic hears her.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.TurnWatcher = api.TurnWatcher;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  const DEFAULTS = {
    silenceMs: 2000, // quiet this long ends the turn
    minSpeechMs: 350, // shorter than this is a cough, not a sentence
    gateBase: 0.018,
    gateSpeaking: 0.05, // higher while her voice is playing: barge-in only
    noiseEma: 0.05, // how fast the room-noise estimate follows the mic
    noiseStart: 0.002,
  };

  class TurnWatcher {
    constructor(opts) {
      this.opts = Object.assign({}, DEFAULTS, opts || {});
      this.reset();
    }

    reset() {
      this.noise = this.opts.noiseStart;
      this.spoke = false;
      this.speechMs = 0;
      this.lastVoice = 0;
      this.everSpoke = false;
    }

    /** @returns {"speech-start"|"turn-end"|null} */
    push(rms, blockMs, now, speaking) {
      const { gateBase, gateSpeaking, noiseEma, minSpeechMs, silenceMs } = this.opts;
      const gate = speaking ? gateSpeaking : Math.max(gateBase, this.noise * 3);

      if (rms < gate) {
        this.noise += (rms - this.noise) * noiseEma;
      } else {
        // the clock starts when this block ends, so the two seconds are two
        // real seconds of quiet after the last sound, not after its first byte
        this.lastVoice = now + blockMs;
        this.speechMs += blockMs;
        if (!this.spoke) {
          this.spoke = true;
          this.everSpoke = true;
          return 'speech-start'; // never also end a turn on the same block
        }
      }

      if (this.spoke && this.speechMs >= minSpeechMs && now - this.lastVoice >= silenceMs) {
        this.spoke = false;
        this.speechMs = 0;
        this.lastVoice = 0;
        return 'turn-end';
      }
      return null;
    }
  }

  return { TurnWatcher, DEFAULTS };
});
