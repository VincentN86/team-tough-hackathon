import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Kitchen, diffOrder } from '../src/kitchen.js';
import { EMPLOYEES, createSampleOrders, seedKitchen, demoUpdateOrder42 } from '../src/sampleData.js';
import { interpretVoiceCommand } from '../src/voice.js';
import { prioritize } from '../src/urgency.js';

const NOW = Date.UTC(2026, 10, 7, 18, 0);

function makeKitchen() {
  let t = NOW;
  const k = new Kitchen({
    employees: EMPLOYEES,
    clock: () => t,
    orders: [{
      id: 'o1', number: '1', platform: 'doordash', status: 'in_progress', receivedAt: NOW - 60_000, promisedAt: NOW + 20 * 60_000, startedAt: NOW,
      items: [
        { id: 'i1', menuKey: 'burger', name: 'Burger', qty: 1, modifiers: [{ id: 'm1', text: 'no onions' }, { id: 'm2', text: 'extra pickles' }] },
        { id: 'i2', menuKey: 'fries', name: 'Fries', qty: 1, modifiers: [{ id: 'm3', text: 'light salt' }] },
      ],
      allergies: [{ id: 'a1', allergen: 'Sesame', itemId: null }],
    }],
  });
  return { k, tick: (ms) => (t += ms) };
}
const maria = { employeeId: 'e-maria', method: 'tap' };

// ---------- gating ----------

test('Ready is blocked until every modifier and allergy is confirmed', () => {
  const { k } = makeKitchen();
  let r = k.advance('o1', maria);
  assert.equal(r.ok, false);
  assert.equal(r.code, 'confirmations_missing');
  assert.equal(r.message, '1 allergy + 3 modifiers unconfirmed');

  k.confirm('o1', 'mod:m1', maria);
  k.confirm('o1', 'mod:m2', maria);
  k.confirm('o1', 'mod:m3', maria);
  assert.equal(k.readyBlockReason('o1'), '1 allergy unconfirmed');
  assert.equal(k.advance('o1', maria).ok, false);

  k.confirm('o1', 'allergy:a1', maria);
  assert.equal(k.readyBlockReason('o1'), null);
  assert.equal(k.advance('o1', maria).ok, true);
  assert.equal(k.getOrder('o1').status, 'ready');
  assert.ok(k.auditLog.some((e) => e.type === 'ready_blocked'));
});

test('manager override needs a manager, the right PIN and a typed reason; it is logged and flagged', () => {
  const { k } = makeKitchen();
  assert.equal(k.overrideReady('o1', { managerId: 'e-maria', pin: '1111', reason: 'rush hour' }).code, 'not_manager');
  assert.equal(k.overrideReady('o1', { managerId: 'e-jordan', pin: '0000', reason: 'rush hour' }).code, 'bad_pin');
  assert.equal(k.overrideReady('o1', { managerId: 'e-jordan', pin: '9999', reason: '  ' }).code, 'reason_required');
  assert.equal(k.getOrder('o1').status, 'in_progress');

  const r = k.overrideReady('o1', { managerId: 'e-jordan', pin: '9999', reason: 'Customer at counter, checked by manager' });
  assert.equal(r.ok, true);
  const o = k.getOrder('o1');
  assert.equal(o.status, 'ready');
  assert.equal(o.override.by, 'e-jordan');
  assert.equal(o.override.reason, 'Customer at counter, checked by manager');
  assert.equal(o.override.unconfirmed.length, 4);
  const log = k.auditLog.find((e) => e.type === 'override');
  assert.equal(log.flagged, true);
  assert.match(log.detail, /Reason: Customer at counter/);
  assert.equal(k.auditLog.filter((e) => e.type === 'override_rejected').length, 3);
});

// ---------- confirmations ----------

test('each confirmation records employee, time, method and transcript; undo is logged', () => {
  const { k, tick } = makeKitchen();
  tick(5000);
  const r = k.confirm('o1', 'mod:m1', { employeeId: 'e-dev', method: 'voice', transcript: 'Order 1, no onions satisfied' });
  assert.equal(r.ok, true);
  assert.deepEqual(
    { by: r.confirmation.employeeId, at: r.confirmation.at, method: r.confirmation.method, transcript: r.confirmation.transcript },
    { by: 'e-dev', at: NOW + 5000, method: 'voice', transcript: 'Order 1, no onions satisfied' },
  );
  const entry = k.auditLog.findLast((e) => e.type === 'confirm');
  assert.equal(entry.transcript, 'Order 1, no onions satisfied');

  assert.equal(k.undoConfirmation('o1', 'mod:m1', { employeeId: 'e-maria' }).ok, true);
  assert.equal(k.progress('o1').confirmed, 0);
  assert.match(k.auditLog.findLast((e) => e.type === 'undo').detail, /Dev Patel/);
});

test('confirming requires a signed-in employee', () => {
  const { k } = makeKitchen();
  assert.equal(k.confirm('o1', 'mod:m1', { method: 'tap' }).code, 'no_employee');
});

test('two employees confirming the same item: first wins, second ignored and logged', () => {
  const { k } = makeKitchen();
  const first = k.confirm('o1', 'mod:m1', { employeeId: 'e-maria', method: 'tap' });
  const second = k.confirm('o1', 'mod:m1', { employeeId: 'e-dev', method: 'voice', transcript: 'order 1 no onions satisfied' });
  assert.equal(first.ok, true);
  assert.equal(second.ok, false);
  assert.equal(second.code, 'already_confirmed');
  assert.equal(k.checklist('o1').find((r) => r.key === 'mod:m1').confirmation.employeeId, 'e-maria');
  const ignored = k.auditLog.find((e) => e.type === 'confirm_ignored');
  assert.equal(ignored.employeeId, 'e-dev');
  assert.match(ignored.detail, /Maria Lopez/);
});

test('confirmAllModifiers never confirms allergies', () => {
  const { k } = makeKitchen();
  const r = k.confirmAllModifiers('o1', maria);
  assert.deepEqual(r.confirmed.sort(), ['mod:m1', 'mod:m2', 'mod:m3']);
  assert.deepEqual(r.skippedAllergies, ['allergy:a1']);
  assert.equal(k.readyBlockReason('o1'), '1 allergy unconfirmed');
});

test('checklist puts allergies first', () => {
  const { k } = makeKitchen();
  assert.equal(k.checklist('o1')[0].type, 'allergy');
});

test('confirmations on Ready/Completed orders are rejected', () => {
  const { k } = makeKitchen();
  k.overrideReady('o1', { managerId: 'e-jordan', pin: '9999', reason: 'test override' });
  assert.equal(k.confirm('o1', 'mod:m1', maria).code, 'order_closed');
  assert.ok(k.auditLog.some((e) => e.type === 'confirm_rejected'));
});

// ---------- order updates ----------

test('order update resets changed confirmations and keeps unchanged ones', () => {
  const { k } = makeKitchen();
  k.confirm('o1', 'mod:m1', maria); // no onions — unchanged
  k.confirm('o1', 'mod:m2', maria); // extra pickles — will change
  k.confirm('o1', 'mod:m3', maria); // light salt — will be removed
  k.confirm('o1', 'allergy:a1', maria);

  const o = k.getOrder('o1');
  const r = k.updateOrder('o1', {
    items: [
      { ...o.items[0], modifiers: [{ id: 'm1', text: 'no onions' }, { id: 'm2', text: 'no pickles' }, { id: 'm4', text: 'no cheese' }] },
      { ...o.items[1], modifiers: [] },
    ],
  });
  assert.equal(r.ok, true);
  const conf = Object.fromEntries(k.checklist('o1').map((row) => [row.key, !!row.confirmation]));
  assert.deepEqual(conf, { 'allergy:a1': true, 'mod:m1': true, 'mod:m2': false, 'mod:m4': false });

  const updated = k.getOrder('o1').updated;
  assert.ok(updated && !updated.acknowledgedAt);
  assert.deepEqual(updated.highlightKeys.sort(), ['mod:m2', 'mod:m4']);
  const kinds = updated.changes.map((c) => `${c.kind}:${c.text}`);
  assert.ok(kinds.includes('changed:no pickles'));
  assert.ok(kinds.includes('added:no cheese'));
  assert.ok(kinds.includes('removed:light salt'));
  assert.ok(k.auditLog.some((e) => e.type === 'confirmation_reset' && e.key === 'mod:m2'));
  assert.ok(k.auditLog.some((e) => e.type === 'order_updated' && e.flagged));
});

test('changing item quantity resets every confirmation on that item only', () => {
  const { k } = makeKitchen();
  k.confirmAllModifiers('o1', maria);
  const o = k.getOrder('o1');
  k.updateOrder('o1', { items: [{ ...o.items[0], qty: 2 }, o.items[1]] });
  const conf = Object.fromEntries(k.checklist('o1').map((row) => [row.key, !!row.confirmation]));
  assert.equal(conf['mod:m1'], false);
  assert.equal(conf['mod:m2'], false);
  assert.equal(conf['mod:m3'], true);
});

test('changed allergy resets; a Ready order with new unconfirmed items reopens to In Progress', () => {
  const { k } = makeKitchen();
  k.confirmAllModifiers('o1', maria);
  k.confirm('o1', 'allergy:a1', maria);
  k.advance('o1', maria);
  assert.equal(k.getOrder('o1').status, 'ready');
  k.updateOrder('o1', { allergies: [{ id: 'a1', allergen: 'Sesame', note: 'severe', itemId: null }] });
  assert.equal(k.getOrder('o1').status, 'in_progress');
  assert.equal(k.readyBlockReason('o1'), '1 allergy unconfirmed');
});

test('diffOrder reports nothing for an identical order', () => {
  const [o] = createSampleOrders(NOW).filter((x) => x.id === 'o42');
  assert.deepEqual(diffOrder(o, structuredClone(o)), { changes: [], resetKeys: [], removedKeys: [] });
});

test('cancel and acknowledge are logged', () => {
  const { k } = makeKitchen();
  k.cancelOrder('o1', { reason: 'Customer cancelled' });
  assert.equal(k.getOrder('o1').status, 'cancelled');
  assert.equal(k.acknowledge('o1', 'cancel', maria).ok, true);
  assert.ok(k.auditLog.some((e) => e.type === 'cancelled'));
  assert.ok(k.auditLog.some((e) => e.type === 'acknowledged'));
});

// ---------- sample data ----------

test('sample data covers the edge cases and ranks B (pizza) above A (sandwich)', () => {
  const k = seedKitchen({ now: NOW, clock: () => NOW });
  const orders = k.listOrders();
  assert.equal(orders.length, 10);
  assert.ok(orders.some((o) => o.promisedAt == null), 'missing promised time');
  assert.ok(orders.some((o) => o.status === 'cancelled'), 'cancelled');
  assert.ok(orders.some((o) => o.status === 'ready' && o.allergies.length), 'ready with allergy');
  assert.ok(orders.some((o) => o.status === 'completed'), 'completed');
  assert.ok(k.getOrder('o43').updated, 'updated after receipt');
  assert.equal(k.checklist('o43').find((r) => r.key === 'mod:o43-1-m1').confirmation, null, 'changed modifier reset');
  assert.ok(k.checklist('o43').find((r) => r.key === 'mod:o43-1-m2').confirmation, 'unchanged modifier kept');

  const board = prioritize(orders, NOW);
  const ids = board.queue.map((e) => e.order.id);
  assert.equal(ids[0], 'o38');
  assert.equal(board.queue[0].ev.level, 'late');
  assert.ok(ids.indexOf('o46') < ids.indexOf('o45'), 'pizza B above sandwich A');
  assert.equal(interpretVoiceCommand('Order 42, no onions satisfied', k.voiceContext()).kind, 'ambiguous');
});

test('demo update on #42 resets the confirmed "extra pickles" when it becomes "no pickles"', () => {
  const k = seedKitchen({ now: NOW, clock: () => NOW });
  assert.ok(k.checklist('o42').find((r) => r.key === 'mod:o42-1-m2').confirmation);
  demoUpdateOrder42(k);
  assert.equal(k.checklist('o42').find((r) => r.key === 'mod:o42-1-m2').confirmation, null);
  assert.ok(k.checklist('o42').find((r) => r.key === 'mod:o42-3-m1').confirmation, 'light salt untouched');
});
