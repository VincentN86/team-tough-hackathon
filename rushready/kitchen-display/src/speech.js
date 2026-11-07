// Thin, mockable wrapper around the browser Web Speech API.
// Push-to-talk: start() on press, stop() on release. The final transcript is
// delivered once via onFinal; live text streams through onInterim.

export function getRecognitionCtor(scope = globalThis) {
  return scope.SpeechRecognition || scope.webkitSpeechRecognition || null;
}

export function createSpeechInput({
  Recognition = getRecognitionCtor(),
  lang = 'en-US',
  onInterim = () => {},
  onFinal = () => {},
  onError = () => {},
  onStateChange = () => {},
} = {}) {
  if (!Recognition) {
    return { supported: false, listening: false, start() {}, stop() {} };
  }
  let rec = null;
  let latest = '';
  const api = {
    supported: true,
    listening: false,
    start() {
      if (api.listening) return;
      latest = '';
      rec = new Recognition();
      rec.lang = lang;
      rec.interimResults = true;
      rec.continuous = true;
      rec.maxAlternatives = 1;
      rec.onresult = (event) => {
        let text = '';
        for (let i = 0; i < event.results.length; i++) text += event.results[i][0].transcript;
        latest = text.trim();
        onInterim(latest);
      };
      rec.onerror = (event) => onError(event.error || 'speech-error');
      rec.onend = () => {
        api.listening = false;
        onStateChange(false);
        const text = latest;
        latest = '';
        rec = null;
        if (text) onFinal(text);
      };
      try {
        rec.start();
        api.listening = true;
        onStateChange(true);
      } catch (err) {
        onError(err?.message || 'could-not-start');
      }
    },
    stop() {
      if (rec) rec.stop();
    },
  };
  return api;
}

/**
 * Minimal fake of the SpeechRecognition class, for tests and demos.
 * const Fake = createFakeRecognition(); ... Fake.instance.emit('Order 42 ...', true); Fake.instance.stop();
 */
export function createFakeRecognition() {
  class FakeRecognition {
    constructor() { FakeRecognition.instance = this; this.results = []; }
    start() { this.started = true; }
    stop() { this.started = false; this.onend?.(); }
    emit(text, isFinal = false) {
      const r = [{ transcript: text }];
      r.isFinal = isFinal;
      this.results = [r];
      this.onresult?.({ results: this.results });
    }
    fail(error) { this.onerror?.({ error }); }
  }
  return FakeRecognition;
}

/** Optional spoken feedback. Silently no-ops where speechSynthesis is missing. */
export function speak(text, { enabled = true, scope = globalThis } = {}) {
  if (!enabled || !scope.speechSynthesis || !scope.SpeechSynthesisUtterance) return;
  try {
    scope.speechSynthesis.cancel();
    const u = new scope.SpeechSynthesisUtterance(text);
    u.rate = 1.05;
    scope.speechSynthesis.speak(u);
  } catch {
    /* audio is optional */
  }
}
