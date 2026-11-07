import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createFakeRecognition, createSpeechInput } from '../src/speech.js';

test('push-to-talk streams interim text and delivers the final transcript on release', () => {
  const Fake = createFakeRecognition();
  const interim = [];
  const finals = [];
  const states = [];
  const input = createSpeechInput({
    Recognition: Fake,
    onInterim: (t) => interim.push(t),
    onFinal: (t) => finals.push(t),
    onStateChange: (s) => states.push(s),
  });
  assert.equal(input.supported, true);
  input.start();
  Fake.instance.emit('order 42');
  Fake.instance.emit('order 42 no onions satisfied', true);
  input.stop();
  assert.deepEqual(interim, ['order 42', 'order 42 no onions satisfied']);
  assert.deepEqual(finals, ['order 42 no onions satisfied']);
  assert.deepEqual(states, [true, false]);
});

test('releasing without speech delivers nothing', () => {
  const Fake = createFakeRecognition();
  const finals = [];
  const input = createSpeechInput({ Recognition: Fake, onFinal: (t) => finals.push(t) });
  input.start();
  input.stop();
  assert.deepEqual(finals, []);
});

test('unsupported browsers get a no-op input so the typed fallback still works', () => {
  const input = createSpeechInput({ Recognition: null });
  assert.equal(input.supported, false);
  input.start();
  input.stop();
});
