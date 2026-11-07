import { test } from 'node:test';
import assert from 'node:assert/strict';
import { MIN, withConfig, DEFAULT_CONFIG } from '../src/config.js';
import { classifySlack, evaluateOrder, planOrderPrep, prioritize, resolvePromisedAt } from '../src/urgency.js';

const T = (h, m) => Date.UTC(2026, 10, 7, h, m);
const clock = (ms) => new Date(ms).toISOString().slice(11, 16);
const order = (id, { items, receivedAt = T(18, 0), promisedAt = T(18, 30), status = 'new', platform = 'instore', ...rest }) => ({
  id, number: id, platform, status, receivedAt, promisedAt, allergies: [],
  items: items.map(([menuKey, qty = 1], i) => ({ id: `${id}-${i}`, menuKey, name: DEFAULT_CONFIG.menu[menuKey].name, qty, modifiers: [] })),
  ...rest,
});

test('worked example: pizza (B) ranks above sandwich (A) even though A arrived first', () => {
  const A = order('A', { receivedAt: T(18, 0), promisedAt: T(18, 30), items: [['turkey-sandwich']] });
  const B = order('B', { receivedAt: T(18, 5), promisedAt: T(18, 30), items: [['margherita-pizza']] });
  const now = T(18, 5);

  const evA = evaluateOrder(A, now, DEFAULT_CONFIG, clock);
  const evB = evaluateOrder(B, now, DEFAULT_CONFIG, clock);
  assert.equal(evA.latestStartAt, T(18, 23));
  assert.equal(evB.latestStartAt, T(18, 8));
  assert.equal(evB.level, 'start_now');
  assert.equal(evA.level, 'on_track');

  const board = prioritize([A, B], now, DEFAULT_CONFIG, clock);
  assert.deepEqual(board.queue.map((e) => e.order.id), ['B', 'A']);
  assert.deepEqual(board.actNow.map((e) => e.order.id), ['B']);
  assert.match(evB.reason, /Margherita pizza takes 20 min/);
  assert.match(evB.reason, /due in 25 min/);
  assert.match(evB.reason, /Start within 3 min/);
});

test('urgency thresholds: Late < 0, Start Now <= 3, Start Soon <= 10, On Track > 10', () => {
  assert.equal(classifySlack(-0.1, 5), 'late');
  assert.equal(classifySlack(0, 5), 'start_now');
  assert.equal(classifySlack(3, 5), 'start_now');
  assert.equal(classifySlack(3.01, 5), 'start_soon');
  assert.equal(classifySlack(10, 15), 'start_soon');
  assert.equal(classifySlack(10.01, 15), 'on_track');
  assert.equal(classifySlack(20, -1), 'late', 'promised time already passed');
});

test('late order reason explains how far past latest start, and overdue orders say overdue', () => {
  const o = order('L', { promisedAt: T(18, 30), items: [['burger']] }); // 8 min + 2 buffer -> latest 18:20
  const ev = evaluateOrder(o, T(18, 24), DEFAULT_CONFIG, clock);
  assert.equal(ev.level, 'late');
  assert.match(ev.reason, /4 min past the latest safe start/);
  const overdue = evaluateOrder(o, T(18, 33), DEFAULT_CONFIG, clock);
  assert.equal(overdue.level, 'late');
  assert.match(overdue.reason, /3 min overdue/);
});

test('buffer is configurable', () => {
  const o = order('X', { items: [['turkey-sandwich']] });
  assert.equal(evaluateOrder(o, T(18, 0), withConfig({ bufferMin: 0 })).latestStartAt, T(18, 25));
  assert.equal(evaluateOrder(o, T(18, 0), withConfig({ bufferMin: 5 })).latestStartAt, T(18, 20));
});

test('prep = longest item across stations; same-station items queue by capacity', () => {
  const mixed = order('M', { items: [['burger'], ['fries']] });
  assert.equal(planOrderPrep(mixed).prepMin, 8);

  const twoPizzas = order('P2', { items: [['margherita-pizza', 2]] });
  assert.equal(planOrderPrep(twoPizzas, withConfig({ stations: { oven: { label: 'Oven', capacity: 1 } } })).prepMin, 40);
  assert.equal(planOrderPrep(twoPizzas).prepMin, 20, 'default oven fits 2');

  const threePizzas = order('P3', { items: [['pepperoni-pizza', 3]] });
  const plan = planOrderPrep(threePizzas);
  assert.equal(plan.prepMin, 40);
  assert.equal(plan.critical.shared, true);
  assert.match(evaluateOrder(threePizzas, T(17, 0)).reason, /3 items share the pizza oven \(2 at a time\)/);
});

test('multi-item orders get staggered start offsets so everything finishes together', () => {
  const o = order('S', { promisedAt: T(19, 0), items: [['lasagna'], ['caesar-salad'], ['garlic-bread']] });
  const plan = planOrderPrep(o);
  assert.equal(plan.prepMin, 18);
  const off = Object.fromEntries(plan.items.map((i) => [i.name, i.startOffsetMin]));
  assert.equal(off['Lasagna'], 0);
  assert.equal(off['Caesar salad'], 14);
  assert.equal(off['Garlic bread'], 12);
  for (const i of plan.items) assert.equal(i.endOffsetMin, 18);
  assert.match(evaluateOrder(o, T(18, 0), DEFAULT_CONFIG, clock).stagger, /Garlic bread at \+12 min \(18:52\), Caesar salad at \+14 min \(18:54\)/);
});

test('missing promised time falls back to the platform SLA and is flagged', () => {
  const o = order('D', { platform: 'doordash', promisedAt: null, receivedAt: T(18, 0), items: [['fries']] });
  const r = resolvePromisedAt(o);
  assert.deepEqual(r, { promisedAt: T(18, 25), estimated: true, slaMin: 25 });
  const ev = evaluateOrder(o, T(18, 0));
  assert.equal(ev.promisedEstimated, true);
  assert.equal(ev.latestStartAt, T(18, 19));
});

test('in-progress tickets are pinned separately in start order, not re-sorted by slack', () => {
  const now = T(18, 10);
  const first = order('first', { status: 'in_progress', startedAt: T(18, 0), promisedAt: T(18, 50), items: [['burger']] });
  const second = order('second', { status: 'in_progress', startedAt: T(18, 5), promisedAt: T(18, 20), items: [['burger']] });
  const fresh = order('fresh', { items: [['burger']] });
  const board = prioritize([second, fresh, first], now);
  assert.deepEqual(board.inProgress.map((e) => e.order.id), ['first', 'second']);
  assert.deepEqual(board.queue.map((e) => e.order.id), ['fresh']);
  const ev = board.inProgress[1].ev;
  assert.equal(ev.level, 'on_track'); // done 18:13, due 18:20
  assert.match(ev.reason, /min spare/);
});

test('in-progress order projected to finish after promised time is Late', () => {
  const o = order('slow', { status: 'in_progress', startedAt: T(18, 20), promisedAt: T(18, 25), items: [['burger']] });
  const ev = evaluateOrder(o, T(18, 21), DEFAULT_CONFIG, clock);
  assert.equal(ev.level, 'late');
  assert.match(ev.reason, /projected 3 min late/);
});

test('ties on slack break by arrival time', () => {
  const later = order('later', { receivedAt: T(18, 2), items: [['burger']] });
  const earlier = order('earlier', { receivedAt: T(18, 1), items: [['burger']] });
  assert.deepEqual(prioritize([later, earlier], T(18, 3)).queue.map((e) => e.order.id), ['earlier', 'later']);
});

test('every evaluated ticket carries an explanation', () => {
  const statuses = ['new', 'in_progress', 'ready', 'completed', 'cancelled'];
  for (const status of statuses) {
    const ev = evaluateOrder(order(status, { status, startedAt: T(18, 0), items: [['burger']] }), T(18, 5));
    assert.ok(ev.reason && ev.reason.length > 10, status);
    assert.ok(ev.label, status);
  }
  assert.equal(MIN, 60000);
});
