// Kitchen state: orders, confirmations, status transitions, gating, updates, audit log.
// Framework-free so it runs in the browser and under `node --test`.

import { DEFAULT_CONFIG, NEXT_STATUS, PREV_STATUS, STATUS, STATUS_LABEL, PLATFORMS } from './config.js';
import { allergyKey, allergyText, buildChecklist, modKey } from './checklist.js';

const CONFIRMABLE = new Set([STATUS.NEW, STATUS.IN_PROGRESS]);
const TRANSITIONS = {
  new: ['in_progress', 'cancelled'],
  in_progress: ['ready', 'new', 'cancelled'],
  ready: ['completed', 'in_progress', 'cancelled'],
  completed: [],
  cancelled: [],
};
const clone = (v) => (typeof structuredClone === 'function' ? structuredClone(v) : JSON.parse(JSON.stringify(v)));
const fail = (code, message, extra = {}) => ({ ok: false, code, message, ...extra });
const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/**
 * Compare two versions of an order.
 * - changed/removed modifier or allergy -> its confirmation resets/drops
 * - item qty/name change -> every checklist row on that item resets
 * - unchanged rows keep their confirmation
 */
export function diffOrder(prev, next) {
  const changes = [];
  const resetKeys = new Set();
  const removedKeys = new Set();
  const prevItems = new Map(prev.items.map((i) => [i.id, i]));
  const nextItemIds = new Set(next.items.map((i) => i.id));
  const changedItemIds = new Set();
  const label = (i) => `${i.qty}× ${i.name}`;

  for (const item of next.items) {
    const old = prevItems.get(item.id);
    if (!old) {
      changes.push({ kind: 'added', target: 'item', itemId: item.id, text: label(item) });
      for (const m of item.modifiers ?? []) {
        changes.push({ kind: 'added', target: 'modifier', itemId: item.id, key: modKey(m.id), text: m.text });
      }
      continue;
    }
    const itemChanged = old.qty !== item.qty || old.name !== item.name || old.menuKey !== item.menuKey;
    if (itemChanged) {
      changedItemIds.add(item.id);
      changes.push({ kind: 'changed', target: 'item', itemId: item.id, text: label(item), previousText: label(old) });
    }
    const oldMods = new Map((old.modifiers ?? []).map((m) => [m.id, m]));
    const newModIds = new Set((item.modifiers ?? []).map((m) => m.id));
    for (const m of item.modifiers ?? []) {
      const key = modKey(m.id);
      const om = oldMods.get(m.id);
      if (!om) {
        changes.push({ kind: 'added', target: 'modifier', itemId: item.id, key, text: m.text });
      } else if (om.text !== m.text) {
        changes.push({ kind: 'changed', target: 'modifier', itemId: item.id, key, text: m.text, previousText: om.text });
        resetKeys.add(key);
      } else if (itemChanged) {
        resetKeys.add(key);
      }
    }
    for (const om of old.modifiers ?? []) {
      if (!newModIds.has(om.id)) {
        changes.push({ kind: 'removed', target: 'modifier', itemId: item.id, key: modKey(om.id), text: om.text });
        removedKeys.add(modKey(om.id));
      }
    }
  }
  for (const old of prev.items) {
    if (nextItemIds.has(old.id)) continue;
    changes.push({ kind: 'removed', target: 'item', itemId: old.id, text: label(old) });
    for (const m of old.modifiers ?? []) removedKeys.add(modKey(m.id));
  }

  const prevAllergies = new Map((prev.allergies ?? []).map((a) => [a.id, a]));
  const nextAllergyIds = new Set((next.allergies ?? []).map((a) => a.id));
  for (const a of next.allergies ?? []) {
    const key = allergyKey(a.id);
    const old = prevAllergies.get(a.id);
    if (!old) {
      changes.push({ kind: 'added', target: 'allergy', itemId: a.itemId ?? null, key, text: allergyText(a) });
    } else if (allergyText(old) !== allergyText(a) || (old.itemId ?? null) !== (a.itemId ?? null)) {
      changes.push({ kind: 'changed', target: 'allergy', itemId: a.itemId ?? null, key, text: allergyText(a), previousText: allergyText(old) });
      resetKeys.add(key);
    } else if (a.itemId && changedItemIds.has(a.itemId)) {
      resetKeys.add(key);
    }
  }
  for (const old of prev.allergies ?? []) {
    if (!nextAllergyIds.has(old.id)) {
      const key = allergyKey(old.id);
      changes.push({ kind: 'removed', target: 'allergy', itemId: old.itemId ?? null, key, text: allergyText(old) });
      removedKeys.add(key);
    }
  }
  return { changes, resetKeys: [...resetKeys], removedKeys: [...removedKeys] };
}

export function describeChange(c) {
  const sign = c.kind === 'added' ? '+' : c.kind === 'removed' ? '−' : '~';
  const what = c.target === 'allergy' ? 'ALLERGY ' : c.target === 'item' ? 'Item ' : '';
  if (c.kind === 'changed') return `${sign} ${what}${c.previousText} → ${c.text}`;
  return `${sign} ${what}${c.text}`;
}

export class Kitchen {
  constructor({ orders = [], employees = [], config = DEFAULT_CONFIG, clock = () => Date.now() } = {}) {
    this.config = config;
    this.clock = clock;
    this.employees = employees;
    this.orders = new Map();
    this.confirmations = new Map(); // orderId -> Map(key -> ModifierConfirmation)
    this.auditLog = [];
    this.listeners = new Set();
    this._seq = 0;
    for (const o of orders) this.addOrder(o, { silent: true });
  }

  // ---------- plumbing ----------
  now() { return this.clock(); }
  subscribe(fn) { this.listeners.add(fn); return () => this.listeners.delete(fn); }
  _emit() { for (const fn of this.listeners) fn(); }
  _log(type, fields = {}) {
    const entry = { id: `log-${++this._seq}`, at: this.now(), type, ...fields };
    this.auditLog.push(entry);
    return entry;
  }
  employee(id) { return this.employees.find((e) => e.id === id) ?? null; }
  employeeName(id) { return this.employee(id)?.name ?? 'Unknown'; }
  getOrder(id) { return this.orders.get(id) ?? null; }
  listOrders() { return [...this.orders.values()]; }
  findByNumber(number) { return this.listOrders().find((o) => String(o.number) === String(number)) ?? null; }
  orderLog(orderId) { return this.auditLog.filter((e) => e.orderId === orderId); }
  _label(order) { return `#${order.number}`; }

  addOrder(order, { silent = false } = {}) {
    const o = clone(order);
    o.status ??= STATUS.NEW;
    o.allergies ??= [];
    o.items = o.items.map((it) => ({ ...it, modifiers: it.modifiers ?? [] }));
    o.updated ??= null;
    o.override ??= null;
    o.version ??= 1;
    this.orders.set(o.id, o);
    this.confirmations.set(o.id, new Map());
    this._log('order_received', {
      orderId: o.id,
      detail: `${PLATFORMS[o.platform]?.label ?? o.platform} order ${this._label(o)}${o.promisedAt ? '' : ' (no promised time; using platform default)'}`,
    });
    if (!silent) this._emit();
    return o;
  }

  /** Snapshot for the pure voice resolver. */
  voiceContext() {
    const confirmations = {};
    for (const [orderId, m] of this.confirmations) confirmations[orderId] = Object.fromEntries(m);
    return { orders: this.listOrders(), confirmations, employees: this.employees };
  }

  // ---------- checklist ----------
  checklist(orderId) {
    const order = this.getOrder(orderId);
    if (!order) return [];
    const confs = this.confirmations.get(orderId);
    return buildChecklist(order).map((r) => ({ ...r, confirmation: confs.get(r.key) ?? null }));
  }

  progress(orderId) {
    const rows = this.checklist(orderId);
    const pending = rows.filter((r) => !r.confirmation);
    return {
      total: rows.length,
      confirmed: rows.length - pending.length,
      pendingModifiers: pending.filter((r) => r.type === 'modifier').length,
      pendingAllergies: pending.filter((r) => r.type === 'allergy').length,
    };
  }

  /** null when Ready is allowed; otherwise a short human reason. */
  readyBlockReason(orderId) {
    const p = this.progress(orderId);
    const parts = [];
    if (p.pendingAllergies) parts.push(plural(p.pendingAllergies, 'allergy', 'allergies'));
    if (p.pendingModifiers) parts.push(plural(p.pendingModifiers, 'modifier'));
    return parts.length ? `${parts.join(' + ')} unconfirmed` : null;
  }

  // ---------- confirmations ----------
  confirm(orderId, key, { employeeId, method = 'tap', transcript = null } = {}) {
    const order = this.getOrder(orderId);
    if (!order) return fail('unknown_order', 'Order not found. Nothing changed.');
    const emp = this.employee(employeeId);
    if (!emp) return fail('no_employee', 'Sign in before confirming.');
    const row = buildChecklist(order).find((r) => r.key === key);
    if (!row) return fail('unknown_item', 'That item is no longer on the ticket. Nothing changed.');
    if (!CONFIRMABLE.has(order.status)) {
      this._log('confirm_rejected', { orderId, key, text: row.text, employeeId, method, transcript, detail: `Order is ${STATUS_LABEL[order.status]}` });
      return fail('order_closed', `Order ${this._label(order)} is ${STATUS_LABEL[order.status]}. Nothing changed.`);
    }
    const confs = this.confirmations.get(orderId);
    const existing = confs.get(key);
    if (existing) {
      // First confirmation wins; the second is ignored but recorded.
      this._log('confirm_ignored', {
        orderId, key, text: row.text, employeeId, method, transcript,
        detail: `Already confirmed by ${this.employeeName(existing.employeeId)}`,
      });
      this._emit();
      return fail('already_confirmed', `Already confirmed by ${this.employeeName(existing.employeeId)}. Your confirmation was not applied (logged).`, { existing });
    }
    const confirmation = { orderId, key, type: row.type, text: row.text, itemId: row.itemId, employeeId, method, transcript, at: this.now() };
    confs.set(key, confirmation);
    this._log('confirm', { orderId, key, text: row.text, itemName: row.itemName, employeeId, method, transcript });
    this._emit();
    return { ok: true, confirmation };
  }

  /** Bulk confirm modifiers only. Allergies are never bulk-confirmed. */
  confirmAllModifiers(orderId, opts = {}) {
    const rows = this.checklist(orderId);
    const targets = rows.filter((r) => r.type === 'modifier' && !r.confirmation);
    const results = targets.map((r) => ({ key: r.key, ...this.confirm(orderId, r.key, opts) }));
    return {
      ok: results.every((r) => r.ok),
      confirmed: results.filter((r) => r.ok).map((r) => r.key),
      skippedAllergies: rows.filter((r) => r.type === 'allergy' && !r.confirmation).map((r) => r.key),
      results,
    };
  }

  undoConfirmation(orderId, key, { employeeId, reason = 'undo' } = {}) {
    const confs = this.confirmations.get(orderId);
    const existing = confs?.get(key);
    if (!existing) return fail('not_confirmed', 'Nothing to undo.');
    if (!this.employee(employeeId)) return fail('no_employee', 'Sign in before changing confirmations.');
    const order = this.getOrder(orderId);
    if (!CONFIRMABLE.has(order.status)) return fail('order_closed', `Order ${this._label(order)} is ${STATUS_LABEL[order.status]}.`);
    confs.delete(key);
    this._log('undo', {
      orderId, key, text: existing.text, employeeId,
      detail: `Removed confirmation by ${this.employeeName(existing.employeeId)} (${existing.method}); ${reason}`,
    });
    this._emit();
    return { ok: true, removed: existing };
  }

  // ---------- status ----------
  setStatus(orderId, next, { employeeId = null, note = '' } = {}) {
    const order = this.getOrder(orderId);
    if (!order) return fail('unknown_order', 'Order not found.');
    if (!TRANSITIONS[order.status]?.includes(next)) {
      return fail('bad_transition', `Can't move ${this._label(order)} from ${STATUS_LABEL[order.status]} to ${STATUS_LABEL[next]}.`);
    }
    if (next === STATUS.READY) {
      const reason = this.readyBlockReason(orderId);
      if (reason) {
        this._log('ready_blocked', { orderId, employeeId, detail: reason });
        return fail('confirmations_missing', reason);
      }
    }
    return this._applyStatus(order, next, employeeId, note);
  }

  _applyStatus(order, next, employeeId, note = '') {
    const from = order.status;
    const t = this.now();
    order.status = next;
    if (next === STATUS.IN_PROGRESS && from === STATUS.NEW) order.startedAt = t;
    if (next === STATUS.NEW) delete order.startedAt;
    if (next === STATUS.READY) order.readyAt = t;
    if (next === STATUS.COMPLETED) order.completedAt = t;
    if (next === STATUS.IN_PROGRESS && from === STATUS.READY) { delete order.readyAt; order.override = null; }
    if (next === STATUS.CANCELLED) { order.cancelledAt = t; order.cancelAcknowledgedAt = null; }
    order.version++;
    this._log(next === STATUS.CANCELLED ? 'cancelled' : 'status', {
      orderId: order.id, employeeId,
      detail: `${STATUS_LABEL[from]} → ${STATUS_LABEL[next]}${note ? ` (${note})` : ''}`,
    });
    this._emit();
    return { ok: true, status: next };
  }

  advance(orderId, opts = {}) {
    const order = this.getOrder(orderId);
    if (!order) return fail('unknown_order', 'Order not found.');
    const next = NEXT_STATUS[order.status];
    if (!next) return fail('bad_transition', `${this._label(order)} is ${STATUS_LABEL[order.status]}.`);
    return this.setStatus(orderId, next, opts);
  }

  stepBack(orderId, opts = {}) {
    const order = this.getOrder(orderId);
    const prev = order && PREV_STATUS[order.status];
    if (!prev) return fail('bad_transition', 'Nothing to step back to.');
    return this.setStatus(orderId, prev, { ...opts, note: 'stepped back' });
  }

  /** Manager-only bypass of the Ready gate. Typed reason required; flagged on the ticket. */
  overrideReady(orderId, { managerId, pin, reason } = {}) {
    const order = this.getOrder(orderId);
    if (!order) return fail('unknown_order', 'Order not found.');
    const mgr = this.employee(managerId);
    const reject = (code, message) => {
      this._log('override_rejected', { orderId, employeeId: managerId ?? null, detail: message });
      return fail(code, message);
    };
    if (!mgr || mgr.role !== 'manager') return reject('not_manager', 'Only a manager can override.');
    if (String(pin ?? '') !== String(mgr.pin)) return reject('bad_pin', 'Manager PIN is incorrect.');
    const why = String(reason ?? '').trim();
    if (why.length < 5) return reject('reason_required', 'Type a reason (at least 5 characters).');
    if (!CONFIRMABLE.has(order.status)) return reject('bad_transition', `${this._label(order)} is ${STATUS_LABEL[order.status]}.`);

    const unconfirmed = this.checklist(orderId).filter((r) => !r.confirmation).map(({ key, text, type }) => ({ key, text, type }));
    order.override = { by: managerId, reason: why, at: this.now(), unconfirmed };
    this._log('override', {
      orderId, employeeId: managerId, flagged: true,
      detail: `Marked Ready with ${plural(unconfirmed.length, 'unconfirmed item')}: ${unconfirmed.map((u) => u.text).join('; ') || 'none'}. Reason: ${why}`,
    });
    if (order.status === STATUS.NEW) order.startedAt = this.now();
    return this._applyStatus(order, STATUS.READY, managerId, 'manager override');
  }

  // ---------- updates & cancellation ----------
  /**
   * Apply an update from the platform (items / allergies / promisedAt).
   * Affected confirmations reset; unchanged ones persist.
   */
  updateOrder(orderId, patch, { source = 'platform' } = {}) {
    const order = this.getOrder(orderId);
    if (!order) return fail('unknown_order', 'Order not found.');
    const next = {
      ...order,
      items: patch.items ? clone(patch.items).map((it) => ({ ...it, modifiers: it.modifiers ?? [] })) : order.items,
      allergies: patch.allergies ? clone(patch.allergies) : order.allergies,
    };
    const { changes, resetKeys, removedKeys } = diffOrder(order, next);
    if ('promisedAt' in patch && patch.promisedAt !== order.promisedAt) {
      changes.push({ kind: 'changed', target: 'promisedAt', text: 'Promised time changed', previousText: String(order.promisedAt) });
    }
    if (!changes.length) return { ok: true, changes: [], resetKeys: [], removedKeys: [] };

    const confs = this.confirmations.get(orderId);
    for (const key of resetKeys) {
      const c = confs.get(key);
      if (c) {
        confs.delete(key);
        this._log('confirmation_reset', { orderId, key, text: c.text, detail: `Reset after order update (was confirmed by ${this.employeeName(c.employeeId)})` });
      }
    }
    for (const key of removedKeys) {
      const c = confs.get(key);
      if (c) {
        confs.delete(key);
        this._log('confirmation_removed', { orderId, key, text: c.text, detail: 'Removed from order by update' });
      }
    }

    order.items = next.items;
    order.allergies = next.allergies;
    if ('promisedAt' in patch) order.promisedAt = patch.promisedAt;
    const prior = order.updated && !order.updated.acknowledgedAt ? order.updated : null;
    const highlight = new Set([...(prior?.highlightKeys ?? []), ...changes.filter((c) => c.key && c.kind !== 'removed').map((c) => c.key), ...resetKeys]);
    order.updated = {
      at: this.now(),
      source,
      changes: [...(prior?.changes ?? []), ...changes],
      highlightKeys: [...highlight],
      acknowledgedAt: null,
      acknowledgedBy: null,
    };
    order.version++;
    this._log('order_updated', { orderId, flagged: true, detail: changes.map(describeChange).join('; ') });

    // A Ready ticket that now has unconfirmed items goes back on the line.
    if (order.status === STATUS.READY && this.readyBlockReason(orderId)) {
      this._applyStatus(order, STATUS.IN_PROGRESS, null, 'reopened: order updated');
    } else {
      this._emit();
    }
    return { ok: true, changes, resetKeys, removedKeys };
  }

  cancelOrder(orderId, { reason = 'Cancelled by customer', employeeId = null } = {}) {
    const order = this.getOrder(orderId);
    if (!order) return fail('unknown_order', 'Order not found.');
    if (order.status === STATUS.CANCELLED || order.status === STATUS.COMPLETED) {
      return fail('bad_transition', `${this._label(order)} is ${STATUS_LABEL[order.status]}.`);
    }
    order.cancelReason = reason;
    return this._applyStatus(order, STATUS.CANCELLED, employeeId, reason);
  }

  acknowledge(orderId, what, { employeeId } = {}) {
    const order = this.getOrder(orderId);
    if (!order) return fail('unknown_order', 'Order not found.');
    if (!this.employee(employeeId)) return fail('no_employee', 'Sign in to acknowledge.');
    if (what === 'update' && order.updated) {
      order.updated.acknowledgedAt = this.now();
      order.updated.acknowledgedBy = employeeId;
    } else if (what === 'cancel' && order.status === STATUS.CANCELLED) {
      order.cancelAcknowledgedAt = this.now();
    } else {
      return fail('nothing_to_ack', 'Nothing to acknowledge.');
    }
    this._log('acknowledged', { orderId, employeeId, detail: what === 'update' ? 'Saw order update' : 'Saw cancellation' });
    this._emit();
    return { ok: true };
  }

  // ---------- voice bookkeeping ----------
  logVoiceRejection({ transcript, code, message, orderId = null, employeeId = null, method = 'voice' }) {
    this._log('voice_rejected', { orderId, employeeId, method, transcript, detail: `${code}: ${message}` });
    this._emit();
  }

  logVoiceCancelled({ transcript, orderId, keys = [], employeeId = null, method = 'voice' }) {
    this._log('voice_cancelled', { orderId, employeeId, method, transcript, detail: `Undone within window: ${keys.join(', ')}` });
    this._emit();
  }
}
