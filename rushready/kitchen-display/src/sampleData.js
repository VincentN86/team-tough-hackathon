// Fictional demo data, relative to `now`, covering the spec's edge cases.

import { MIN } from './config.js';
import { Kitchen } from './kitchen.js';

export const EMPLOYEES = [
  { id: 'e-maria', name: 'Maria Lopez', initials: 'ML', role: 'cook', pin: '1111' },
  { id: 'e-dev', name: 'Dev Patel', initials: 'DP', role: 'cook', pin: '2222' },
  { id: 'e-sam', name: 'Sam Kim', initials: 'SK', role: 'expo', pin: '3333' },
  { id: 'e-jordan', name: 'Jordan Reyes', initials: 'JR', role: 'manager', pin: '9999' },
];

const item = (id, menuKey, name, qty, mods = []) => ({
  id, menuKey, name, qty,
  modifiers: mods.map((text, i) => ({ id: `${id}-m${i + 1}`, text })),
});

export function createSampleOrders(now) {
  const at = (min) => now + min * MIN;
  return [
    // Completed earlier, so voice commands for it are rejected.
    {
      id: 'o37', number: '37', platform: 'instore', status: 'completed',
      receivedAt: at(-40), promisedAt: at(-15), startedAt: at(-32), readyAt: at(-20), completedAt: at(-16),
      items: [item('o37-1', 'pad-thai', 'Pad thai', 1, ['mild spice'])],
    },
    // LATE: burger needs 8 + 2 buffer, due in 6 -> 4 min past latest start.
    {
      id: 'o38', number: '38', platform: 'ubereats', customer: 'Avery',
      receivedAt: at(-20), promisedAt: at(6),
      items: [item('o38-1', 'burger', 'Burger', 1, ['no tomato']), item('o38-2', 'fries', 'Fries', 1, ['extra crispy'])],
    },
    // READY with a severe allergy that stays visible.
    {
      id: 'o39', number: '39', platform: 'phone', status: 'ready', customer: 'Chen',
      receivedAt: at(-24), promisedAt: at(3), startedAt: at(-12), readyAt: at(-2),
      items: [item('o39-1', 'chicken-tenders', 'Chicken tenders', 2, ['honey mustard on side'])],
      allergies: [{ id: 'o39-a1', allergen: 'Peanut', severity: 'severe', note: 'clean fryer oil only', itemId: null }],
    },
    // Cancelled after receipt; stays on the board until someone acknowledges it.
    {
      id: 'o41', number: '41', platform: 'grubhub',
      receivedAt: at(-10), promisedAt: at(20),
      items: [item('o41-1', 'salmon', 'Grilled salmon', 1, ['sauce on side'])],
    },
    // IN PROGRESS, many modifiers, two "no onions", order-wide + item-level allergies.
    {
      id: 'o42', number: '42', platform: 'doordash', status: 'in_progress', customer: 'Riley',
      receivedAt: at(-14), promisedAt: at(12), startedAt: at(-4),
      items: [
        item('o42-1', 'burger', 'Burger', 1, ['no onions', 'extra pickles', 'sub gluten-free bun']),
        item('o42-2', 'chicken-sandwich', 'Chicken sandwich', 1, ['no onions', 'add bacon']),
        item('o42-3', 'fries', 'Fries', 1, ['light salt']),
      ],
      allergies: [
        { id: 'o42-a1', allergen: 'Sesame', severity: 'severe', note: 'no sesame buns or oil', itemId: null },
        { id: 'o42-a2', allergen: 'Gluten', severity: 'standard', note: 'GF bun, clean board', itemId: 'o42-1' },
      ],
    },
    // IN PROGRESS, gets UPDATED after confirmations were made (see seedKitchen).
    {
      id: 'o43', number: '43', platform: 'ubereats', status: 'in_progress',
      receivedAt: at(-12), promisedAt: at(10), startedAt: at(-6),
      items: [
        item('o43-1', 'pad-thai', 'Pad thai', 1, ['extra sauce', 'no egg']),
        item('o43-2', 'spring-rolls', 'Spring rolls', 1, ['sweet chili sauce']),
      ],
    },
    // MISSING promised time -> DoorDash default SLA (25 min).
    {
      id: 'o44', number: '44', platform: 'doordash',
      receivedAt: at(-3), promisedAt: null,
      items: [item('o44-1', 'kids-pasta', 'Kids pasta', 2, ['butter only']), item('o44-2', 'garlic-bread', 'Garlic bread', 1)],
    },
    // Worked example, Order A: arrived first, 5-min sandwich, due in 24 -> latest start in 17.
    {
      id: 'o45', number: '45', platform: 'instore',
      receivedAt: at(-6), promisedAt: at(24),
      items: [item('o45-1', 'turkey-sandwich', 'Turkey sandwich', 1, ['no mayo'])],
    },
    // Worked example, Order B: arrived later, 20-min pizza, same due time -> latest start in 2. Ranks above A.
    {
      id: 'o46', number: '46', platform: 'website',
      receivedAt: at(-1), promisedAt: at(24),
      items: [item('o46-1', 'margherita-pizza', 'Margherita pizza', 1, ['extra basil'])],
    },
    // Station capacity + staggering: 3 pizzas on a 2-slot oven = 40 min; salad and bread start late.
    {
      id: 'o47', number: '47', platform: 'phone', customer: 'Sam',
      receivedAt: at(-2), promisedAt: at(52),
      items: [
        item('o47-1', 'pepperoni-pizza', 'Pepperoni pizza', 3, ['well done']),
        item('o47-2', 'caesar-salad', 'Caesar salad', 1, ['dressing on side']),
        item('o47-3', 'garlic-bread', 'Garlic bread', 1),
      ],
      allergies: [{ id: 'o47-a1', allergen: 'Fish', severity: 'standard', note: 'no anchovy in dressing', itemId: 'o47-2' }],
    },
  ];
}

/** Build a Kitchen with sample orders and replay a few events so the board starts realistic. */
export function seedKitchen({ now = Date.now(), clock = () => Date.now(), config } = {}) {
  const kitchen = new Kitchen({ orders: createSampleOrders(now), employees: EMPLOYEES, clock, ...(config ? { config } : {}) });
  const by = (employeeId) => ({ employeeId, method: 'tap' });
  const seedConfirm = (orderId, key, employeeId, status) => {
    // Seeded orders may already be closed; confirm while open, then restore status.
    const o = kitchen.getOrder(orderId);
    const prev = o.status;
    o.status = status ?? 'in_progress';
    kitchen.confirm(orderId, key, by(employeeId));
    o.status = prev;
  };

  seedConfirm('o37', 'mod:o37-1-m1', 'e-maria');
  seedConfirm('o39', 'allergy:o39-a1', 'e-sam');
  seedConfirm('o39', 'mod:o39-1-m1', 'e-sam');

  kitchen.confirm('o42', 'mod:o42-1-m2', by('e-dev'));
  kitchen.confirm('o42', 'mod:o42-3-m1', { employeeId: 'e-maria', method: 'voice', transcript: 'Order 42, light salt satisfied' });

  kitchen.confirm('o43', 'mod:o43-1-m1', by('e-maria'));
  kitchen.confirm('o43', 'mod:o43-1-m2', by('e-maria'));
  kitchen.confirm('o43', 'mod:o43-2-m1', by('e-dev'));
  const o43 = kitchen.getOrder('o43');
  kitchen.updateOrder('o43', {
    items: [
      { ...o43.items[0], modifiers: [{ id: 'o43-1-m1', text: 'sauce on side' }, { id: 'o43-1-m2', text: 'no egg' }, { id: 'o43-1-m3', text: 'add tofu' }] },
      o43.items[1],
    ],
  }, { source: 'Uber Eats' });

  kitchen.cancelOrder('o41', { reason: 'Customer cancelled on Grubhub' });
  return kitchen;
}

// ---------- demo scenarios for the "Demo tools" panel ----------

export function demoUpdateOrder42(kitchen) {
  const o = kitchen.getOrder('o42');
  if (!o || o.status === 'completed' || o.status === 'cancelled') return { ok: false, message: 'Order #42 is not active.' };
  const items = o.items.map((it) => {
    if (it.id === 'o42-1') {
      return { ...it, modifiers: it.modifiers.map((m) => (m.id === 'o42-1-m2' ? { ...m, text: 'no pickles' } : m)).concat(
        it.modifiers.some((m) => m.id === 'o42-1-m4') ? [] : [{ id: 'o42-1-m4', text: 'no cheese' }]) };
    }
    return it;
  });
  return kitchen.updateOrder('o42', { items }, { source: 'DoorDash' });
}

const RUSH_MENU = [
  ['burger', 'Burger', ['no onions', 'extra cheese', 'medium well']],
  ['fries', 'Fries', ['no salt', 'extra crispy']],
  ['margherita-pizza', 'Margherita pizza', ['extra basil', 'light cheese']],
  ['pad-thai', 'Pad thai', ['no peanuts', 'extra lime']],
  ['caesar-salad', 'Caesar salad', ['dressing on side', 'no croutons']],
  ['chicken-tenders', 'Chicken tenders', ['ranch on side']],
  ['salmon', 'Grilled salmon', ['no butter']],
];
const RUSH_PLATFORMS = ['doordash', 'ubereats', 'instore', 'phone', 'website', 'grubhub'];

let rushCounter = 60;
export function createRushOrders(now, count = 8) {
  const orders = [];
  for (let k = 0; k < count; k++) {
    const n = rushCounter++;
    const a = RUSH_MENU[(n * 3) % RUSH_MENU.length];
    const b = RUSH_MENU[(n * 5 + 1) % RUSH_MENU.length];
    const items = [item(`r${n}-1`, a[0], a[1], 1 + (n % 2), [a[2][n % a[2].length]])];
    if (b[0] !== a[0]) items.push(item(`r${n}-2`, b[0], b[1], 1, k % 3 === 0 ? [] : [b[2][0]]));
    orders.push({
      id: `r${n}`, number: String(n), platform: RUSH_PLATFORMS[n % RUSH_PLATFORMS.length],
      receivedAt: now - (k % 3) * MIN,
      promisedAt: k === 4 ? null : now + (12 + ((n * 7) % 30)) * MIN,
      items,
      allergies: k % 4 === 1 ? [{ id: `r${n}-a1`, allergen: k % 8 === 1 ? 'Tree nut' : 'Dairy', severity: 'severe', note: '', itemId: null }] : [],
    });
  }
  return orders;
}
