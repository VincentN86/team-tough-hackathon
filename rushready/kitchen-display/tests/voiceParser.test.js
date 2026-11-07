import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  interpretVoiceCommand, isReadBackConfirmation, parseVoiceCommand, resolveVoiceCommand, wordsToNumber,
} from '../src/voice.js';
import { EMPLOYEES } from '../src/sampleData.js';

const mods = (id, list) => list.map((text, i) => ({ id: `${id}-m${i + 1}`, text }));
const ORDERS = [
  {
    id: 'o42', number: '42', status: 'in_progress',
    items: [
      { id: 'b', name: 'Burger', qty: 1, modifiers: mods('b', ['no onions', 'extra pickles']) },
      { id: 'c', name: 'Chicken sandwich', qty: 1, modifiers: mods('c', ['no onions', 'add bacon']) },
      { id: 'f', name: 'Fries', qty: 1, modifiers: mods('f', ['light salt']) },
    ],
    allergies: [{ id: 'a1', allergen: 'Sesame', note: 'no sesame buns', itemId: null }],
  },
  {
    id: 'o17', number: '17', status: 'new',
    items: [
      { id: 'w', name: 'Wings', qty: 1, modifiers: mods('w', ['extra sauce', 'no sauce on celery']) },
      { id: 's', name: 'Salad', qty: 1, modifiers: mods('s', ['sauce on side']) },
    ],
    allergies: [],
  },
  { id: 'o9', number: '9', status: 'new', items: [{ id: 'p', name: 'Pizza', qty: 1, modifiers: [] }], allergies: [{ id: 'a9', allergen: 'Peanut', itemId: null }] },
  { id: 'o39', number: '39', status: 'ready', items: [{ id: 't', name: 'Tenders', qty: 1, modifiers: mods('t', ['ranch']) }], allergies: [] },
  { id: 'o37', number: '37', status: 'completed', items: [{ id: 'x', name: 'Pad thai', qty: 1, modifiers: mods('x', ['mild']) }], allergies: [] },
  { id: 'o41', number: '41', status: 'cancelled', items: [{ id: 'y', name: 'Salmon', qty: 1, modifiers: mods('y', ['no butter']) }], allergies: [] },
];
const ctx = (confirmations = {}) => ({ orders: ORDERS, confirmations, employees: EMPLOYEES });

// ---------- parsing ----------

test('parses the canonical command', () => {
  const p = parseVoiceCommand('Order 42, no onions satisfied');
  assert.equal(p.ok, true);
  assert.equal(p.orderNumber, '42');
  assert.equal(p.modifierText, 'no onions');
  assert.equal(p.isAll, false);
});

test('parses spoken numbers, "number", filler words and punctuation', () => {
  assert.equal(parseVoiceCommand('order forty two no onions satisfied').orderNumber, '42');
  assert.equal(parseVoiceCommand('Order number 17: extra sauce is satisfied.').modifierText, 'extra sauce');
  assert.equal(parseVoiceCommand('order #17 extra sauce satisfied').orderNumber, '17');
  assert.equal(parseVoiceCommand('OK so order 4 2 light salt satisfied').orderNumber, '42');
  assert.equal(parseVoiceCommand('order 42 two eggs satisfied').modifierText, 'two eggs', 'digits stop number capture');
});

test('wordsToNumber handles common spoken forms', () => {
  assert.equal(wordsToNumber(['forty', 'two']), '42');
  assert.equal(wordsToNumber(['four', 'two']), '42');
  assert.equal(wordsToNumber(['one', 'forty', 'two']), '142');
  assert.equal(wordsToNumber(['one', 'hundred', 'forty', 'two']), '142');
  assert.equal(wordsToNumber(['one', 'hundred', 'and', 'five']), '105');
  assert.equal(wordsToNumber(['twelve']), '12');
  assert.equal(wordsToNumber(['onions']), null);
});

test('syntax errors are reported without guessing', () => {
  assert.equal(parseVoiceCommand('').code, 'empty');
  assert.equal(parseVoiceCommand('no onions satisfied').code, 'unrecognized');
  assert.equal(parseVoiceCommand('order no onions satisfied').code, 'no_order_number');
  assert.equal(parseVoiceCommand('order 42 no onions').code, 'missing_keyword');
  assert.equal(parseVoiceCommand('order 42 satisfied').code, 'missing_modifier');
});

test('"all modifiers satisfied" is recognised in several phrasings', () => {
  for (const t of ['Order 42, all modifiers satisfied', 'order 42 all satisfied', 'order 42 everything is satisfied', 'order 42 all the mods are done']) {
    assert.equal(parseVoiceCommand(t).isAll, true, t);
  }
});

// ---------- resolving ----------

test('valid command resolves to exactly one checklist item', () => {
  const r = interpretVoiceCommand('Order 17, extra sauce satisfied', ctx());
  assert.equal(r.ok, true);
  assert.equal(r.kind, 'single');
  assert.equal(r.target.key, 'mod:w-m1');
  assert.equal(r.requiresSecondStep, false);
  assert.match(r.heard, /Order 17 – extra sauce \(Wings\) – satisfied/);
});

test('fuzzy matches: plural/singular, filler words, small mishears', () => {
  assert.equal(interpretVoiceCommand('Order 42 light salts satisfied', ctx()).target.key, 'mod:f-m1');
  assert.equal(interpretVoiceCommand('order 17 sauce on the side satisfied', ctx()).target.key, 'mod:s-m1');
  assert.equal(interpretVoiceCommand('order 42 extra pickle satisfied', ctx()).target.key, 'mod:b-m2');
  assert.equal(interpretVoiceCommand('order 42 add bakon satisfied', ctx()).target.key, 'mod:c-m2');
});

test('qualifiers must agree: "extra sauce" never matches "no sauce" or "sauce on side"', () => {
  const r = interpretVoiceCommand('order 17 extra sauce satisfied', ctx());
  assert.equal(r.target.key, 'mod:w-m1');
  const none = interpretVoiceCommand('order 17 no sauce satisfied', ctx());
  assert.notEqual(none.ok && none.target?.key, 'mod:w-m1');
});

test('ambiguous modifier asks instead of guessing', () => {
  const r = interpretVoiceCommand('Order 42, no onions satisfied', ctx());
  assert.equal(r.ok, false);
  assert.equal(r.kind, 'ambiguous');
  assert.equal(r.message, "Order 42 has two 'no onions'. Which item?");
  assert.deepEqual(r.candidates.map((c) => c.key).sort(), ['mod:b-m1', 'mod:c-m1']);
});

test('saying the item name resolves the ambiguity', () => {
  assert.equal(interpretVoiceCommand('order 42 chicken sandwich no onions satisfied', ctx()).target.key, 'mod:c-m1');
  assert.equal(interpretVoiceCommand('order 42 burger no onion satisfied', ctx()).target.key, 'mod:b-m1');
});

test('unknown order number and unknown modifier change nothing', () => {
  const a = interpretVoiceCommand('Order 99, no onions satisfied', ctx());
  assert.equal(a.ok, false);
  assert.equal(a.code, 'unknown_order');
  assert.match(a.message, /Order 99 not found/);
  const b = interpretVoiceCommand('Order 42, no pickles please satisfied', ctx());
  assert.equal(b.code, 'unknown_modifier');
  assert.match(b.message, /Nothing changed/);
});

test('orders that are Ready, Completed or Cancelled are rejected', () => {
  assert.equal(interpretVoiceCommand('order 39 ranch satisfied', ctx()).code, 'order_closed');
  assert.match(interpretVoiceCommand('order 39 ranch satisfied', ctx()).message, /already Ready/);
  assert.match(interpretVoiceCommand('order 37 mild satisfied', ctx()).message, /already Completed/);
  assert.equal(interpretVoiceCommand('order 41 no butter satisfied', ctx()).code, 'order_cancelled');
});

test('"all modifiers satisfied" bulk-confirms modifiers but never allergies', () => {
  const r = interpretVoiceCommand('Order 42, all modifiers satisfied', ctx());
  assert.equal(r.ok, true);
  assert.equal(r.kind, 'all');
  assert.equal(r.targets.length, 5);
  assert.ok(r.targets.every((t) => t.type === 'modifier'));
  assert.deepEqual(r.remainingAllergies.map((a) => a.key), ['allergy:a1']);
  assert.match(r.message, /1 allergy item still needs individual confirmation/);
});

test('"all" on an order with only allergies left is refused with instructions', () => {
  const r = interpretVoiceCommand('order 9 all modifiers satisfied', ctx());
  assert.equal(r.ok, false);
  assert.equal(r.code, 'allergy_bulk_blocked');
  assert.match(r.message, /one at a time/);
  assert.match(r.message, /peanut allergy satisfied/);
});

test('"all" skips modifiers that are already confirmed', () => {
  const r = interpretVoiceCommand('order 42 all satisfied', ctx({ o42: { 'mod:b-m1': { employeeId: 'e-dev' } } }));
  assert.equal(r.targets.length, 4);
});

test('an allergy can be confirmed individually but requires a second step', () => {
  const r = interpretVoiceCommand('Order 42, sesame allergy satisfied', ctx());
  assert.equal(r.ok, true);
  assert.equal(r.target.type, 'allergy');
  assert.equal(r.requiresSecondStep, true);
  assert.equal(interpretVoiceCommand('order 9 peanut satisfied', ctx()).target.key, 'allergy:a9');
});

test('already-confirmed item reports who confirmed it', () => {
  const r = interpretVoiceCommand('order 42 light salt satisfied', ctx({ o42: { 'mod:f-m1': { employeeId: 'e-maria' } } }));
  assert.equal(r.code, 'already_confirmed');
  assert.match(r.message, /Maria Lopez/);
});

test('resolveVoiceCommand passes parse errors through untouched', () => {
  const p = parseVoiceCommand('order 42 no onions');
  assert.equal(resolveVoiceCommand(p, ctx()), p);
});

test('read-back confirmation phrases', () => {
  for (const t of ['confirm', 'Yes, confirm.', 'confirmed', 'yes']) assert.equal(isReadBackConfirmation(t), true, t);
  for (const t of ['order 42 confirm', 'cancel', 'no']) assert.equal(isReadBackConfirmation(t), false, t);
});
