/* Turn coordination for the live voice agent — DOM-free so node can test it.
 *
 * Two things go wrong in a naive always-on loop, and both are about a reply
 * that arrives at the wrong moment:
 *
 *   1. The learner starts a new sentence while she is still thinking. Her
 *      answer then lands on top of him, mid-sentence. Whatever he said before
 *      was a fragment, so it should not be answered on its own either.
 *   2. A short think (> 2 s silence, MID-SENTENCE) closes his utterance and
 *      sends half a thought; the rest arrives as a second turn and gets
 *      corrected as if it were a separate sentence.
 *
 * The rule this module implements:
 *
 *   - speech that starts while a turn is IN FLIGHT (thinking, nothing heard
 *     yet) SUPERSEDES that turn: her reply is held, not played, and his text
 *     is carried forward and merged into the next turn — which is sent with
 *     `replace: true` so the server forgets the fragment instead of keeping a
 *     duplicate of it in the conversation history;
 *   - speech that starts while she is SPEAKING is an ordinary barge-in: cut
 *     her off, keep the ear, no merging (he has heard her answer);
 *   - if the "continuation" turns out to be nothing (a cough, a false trigger),
 *     the held reply is restored, so no turn is ever lost.
 */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.TurnCoordinator = api.TurnCoordinator;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  class TurnCoordinator {
    constructor() {
      this.token = 0;
      this.inflight = null; // { token, text, replace } — sent, reply not handled yet
      this.carry = ''; // the learner's words from a superseded turn
      this.held = null; // { token } — a reply received but not played
      this.superseded = new Set();
    }

    reset() {
      this.token = 0;
      this.inflight = null;
      this.carry = '';
      this.held = null;
      this.superseded.clear();
    }

    /** Hand a finished utterance to the coordinator; returns what to send. */
    begin(text) {
      const extra = String(text || '').trim();
      const merged = [this.carry, extra].filter(Boolean).join(' ').trim();
      this.token += 1;
      const turn = {
        token: this.token,
        text: merged,
        replace: Boolean(this.carry), // the fragment is already in her history
      };
      this.carry = '';
      this.held = null; // a held reply is stale once a new turn goes out
      this.inflight = turn;
      return turn;
    }

    /**
     * The learner started talking.
     * @param {string} phase current UI phase: thinking | speaking | hearing | listening
     * @returns {"supersede"|"barge"|"none"}
     */
    onSpeechStart(phase) {
      if (phase === 'thinking' && this.inflight && !this.superseded.has(this.inflight.token)) {
        this.superseded.add(this.inflight.token);
        this.carry = this.inflight.text; // answered again as part of the next turn
        this.held = null;
        return 'supersede';
      }
      if (phase === 'speaking') return 'barge';
      return 'none';
    }

    /**
     * A reply arrived for `token`.
     * @returns {"play"|"hold"} hold = keep it and play it only if the
     *          continuation turns out to be nothing.
     */
    onReply(token) {
      if (this.superseded.has(token)) {
        this.held = { token };
        return 'hold';
      }
      this.inflight = null;
      return 'play';
    }

    /**
     * The learner's utterance closed with `text` (empty = nothing was heard).
     * @returns {{token:number,text:string,replace:boolean}|{restore:number}|null}
     */
    onUtterance(text) {
      const extra = String(text || '').trim();
      if (extra) return this.begin(extra);
      const token = this.restore();
      return token === null ? null : { restore: token };
    }

    /** Nothing heard after all: give the held reply its moment. */
    restore() {
      if (!this.held || !this.carry) return null;
      const { token } = this.held;
      this.held = null;
      this.carry = '';
      this.superseded.delete(token);
      this.inflight = null;
      return token;
    }

    /** The reply was played; the turn is done. */
    settle(token) {
      this.superseded.delete(token);
      if (this.inflight && this.inflight.token === token) this.inflight = null;
      if (this.held && this.held.token === token) this.held = null;
    }

    get pendingText() {
      return this.carry;
    }
  }

  return { TurnCoordinator };
});
