// Kitchen display UI. Wires the pure modules (urgency, voice, kitchen) to the DOM.

import { DEFAULT_CONFIG, MIN, PLATFORMS, STATUS_LABEL } from './config.js';
import { prioritize, LEVELS } from './urgency.js';
import { interpretVoiceCommand, isReadBackConfirmation } from './voice.js';
import { createSpeechInput, speak } from './speech.js';
import { describeChange } from './kitchen.js';
import { EMPLOYEES, createRushOrders, demoUpdateOrder42, seedKitchen } from './sampleData.js';

const config = DEFAULT_CONFIG;
const $ = (sel, root = document) => root.querySelector(sel);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

const storage = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* optional */ } },
};

// Demo clock: real time plus an offset so "time travel" can show re-sorting.
let clockOffset = 0;
const now = () => Date.now() + clockOffset;
const fmtClock = (ms) => new Date(ms).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
const fmtClockSec = (ms) => new Date(ms).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', second: '2-digit' });
function fmtCountdown(ms) {
  const neg = ms < 0;
  let s = Math.floor(Math.abs(ms) / 1000);
  const m = Math.floor(s / 60);
  s %= 60;
  return `${neg ? '+' : ''}${m}:${String(s).padStart(2, '0')}`;
}

const ICONS = {
  late: '<path d="M7.86 2h8.28L22 7.86v8.28L16.14 22H7.86L2 16.14V7.86z"/><path d="M12 8v4M12 16h.01"/>',
  start_now: '<path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.07-2.14-.22-4.05 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.15.43-2.29 1-3a2.5 2.5 0 0 0 2.5 2.5z"/>',
  start_soon: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  on_track: '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
  ready: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
  completed: '<path d="M20 6 9 17l-5-5"/>',
  cancelled: '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6M9 9l6 6"/>',
  allergy: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4M12 17h.01"/>',
  mic: '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v3"/>',
  lock: '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
  play: '<path d="m6 3 14 9-14 9z"/>',
  updated: '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  back: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
};
const icon = (name) => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] ?? ''}</svg>`;

// ---------- state ----------
let kitchen;
let unsubscribe = () => {};
let speech = { supported: false, start() {}, stop() {} };
const ui = {
  employeeId: EMPLOYEES.some((e) => e.id === storage.get('kds.employee')) ? storage.get('kds.employee') : null,
  rushMode: storage.get('kds.rush') ?? 'auto', // auto | on | off
  sound: storage.get('kds.sound') === 'on',
  expanded: new Set(),
  pending: null, // voice confirmation inside its undo window
  allergyPending: null, // allergy awaiting read-back / tap
  afterLogin: null,
  board: null,
  lastLevels: new Map(),
  nextResortAt: 0,
};
const ticketEls = new Map();

function boot() {
  unsubscribe();
  kitchen = seedKitchen({ now: now(), clock: now });
  unsubscribe = kitchen.subscribe(scheduleRender);
  ui.expanded.clear();
  ui.lastLevels.clear();
  cancelPending(false);
  for (const el of ticketEls.values()) el.remove();
  ticketEls.clear();
  renderBoard();
}

const employee = () => EMPLOYEES.find((e) => e.id === ui.employeeId) ?? null;
const shortName = (id) => {
  const e = EMPLOYEES.find((x) => x.id === id);
  if (!e) return 'Unknown';
  const [first, last] = e.name.split(' ');
  return `${first} ${last ? `${last[0]}.` : ''}`.trim();
};
const activeCount = () => kitchen.listOrders().filter((o) => o.status === 'new' || o.status === 'in_progress').length;
const isRush = () => ui.rushMode === 'on' || (ui.rushMode === 'auto' && activeCount() >= config.rushThreshold);

// ---------- rendering ----------
let renderQueued = false;
function scheduleRender() {
  if (renderQueued) return;
  renderQueued = true;
  requestAnimationFrame(() => { renderQueued = false; renderBoard(); });
}

function renderBoard() {
  ui.board = prioritize(kitchen.listOrders(), now(), config, fmtClock);
  ui.nextResortAt = Date.now() + config.refreshSec * 1000;
  document.body.classList.toggle('rush', isRush());

  const unackedCancel = ui.board.cancelled.filter((e) => !e.order.cancelAcknowledgedAt);
  const ackedCancel = ui.board.cancelled.filter((e) => e.order.cancelAcknowledgedAt);
  const lanes = {
    act: [...unackedCancel, ...ui.board.actNow],
    next: ui.board.upNext,
    cooking: ui.board.inProgress,
    ready: ui.board.ready,
    done: [...ackedCancel, ...ui.board.completed],
  };

  const first = new Map();
  for (const [id, el] of ticketEls) if (el.isConnected) first.set(id, el.getBoundingClientRect());

  const placed = new Set();
  for (const [lane, entries] of Object.entries(lanes)) {
    const section = $(`[data-lane="${lane}"]`);
    const grid = $('.lane-grid', section);
    section.dataset.empty = entries.length ? 'false' : 'true';
    $('.lane-count', section).textContent = entries.length;
    entries.forEach((entry, idx) => {
      const id = entry.order.id;
      placed.add(id);
      let el = ticketEls.get(id);
      if (!el) {
        el = document.createElement('article');
        el.dataset.id = id;
        ticketEls.set(id, el);
      }
      const { html, className } = ticketView(entry, lane);
      if (el._html !== html) { el.innerHTML = html; el._html = html; }
      el.className = className;
      if (grid.children[idx] !== el) grid.insertBefore(el, grid.children[idx] ?? null);

      const prev = ui.lastLevels.get(id);
      const rank = LEVELS[entry.ev.level].rank;
      if (prev != null && rank < prev && !reducedMotion) {
        el.classList.remove('escalated');
        void el.offsetWidth;
        el.classList.add('escalated');
      }
      ui.lastLevels.set(id, rank);
    });
  }
  for (const [id, el] of ticketEls) {
    if (!placed.has(id)) { el.remove(); ticketEls.delete(id); }
  }

  if (!reducedMotion) {
    for (const [id, el] of ticketEls) {
      const a = first.get(id);
      const b = el.getBoundingClientRect();
      if (!a) {
        el.animate([{ opacity: 0, transform: 'scale(.96)' }, { opacity: 1, transform: 'none' }], { duration: 320, easing: 'ease-out' });
        continue;
      }
      const dx = a.left - b.left;
      const dy = a.top - b.top;
      if (Math.abs(dx) > 1 || Math.abs(dy) > 1) {
        el.animate([{ transform: `translate(${dx}px, ${dy}px)` }, { transform: 'none' }], { duration: 550, easing: 'cubic-bezier(.2,.8,.2,1)' });
      }
    }
  }
  renderHeader();
  tick();
}

function renderHeader() {
  const b = ui.board;
  const late = b.queue.filter((e) => e.ev.level === 'late').length + b.inProgress.filter((e) => e.ev.level === 'late').length;
  const startNow = b.queue.filter((e) => e.ev.level === 'start_now').length;
  $('#summary').innerHTML = [
    late ? `<span class="pill late">${icon('late')} ${late} late</span>` : '',
    startNow ? `<span class="pill now">${icon('start_now')} ${startNow} start now</span>` : '',
    `<span class="pill cook">${b.inProgress.length} cooking</span>`,
    b.ready.length ? `<span class="pill ready">${icon('ready')} ${b.ready.length} ready</span>` : '',
    isRush() ? '<span class="pill rush">RUSH MODE</span>' : '',
  ].join('');
  $('#rushToggle').textContent = `Rush: ${ui.rushMode === 'auto' ? `Auto (${config.rushThreshold}+)` : ui.rushMode === 'on' ? 'On' : 'Off'}`;
  $('#soundToggle').textContent = ui.sound ? 'Sound on' : 'Sound off';
  $('#soundToggle').setAttribute('aria-pressed', String(ui.sound));
  const emp = employee();
  $('#employeeBtn').textContent = emp ? `${emp.initials} · ${shortName(emp.id)} (${emp.role})` : 'Sign in';
}

function tick() {
  const t = now();
  $('#clock').textContent = fmtClockSec(t);
  for (const el of document.querySelectorAll('[data-due]')) {
    const ms = Number(el.dataset.due) - t;
    el.textContent = ms >= 0 ? `${fmtCountdown(ms)} left` : `${fmtCountdown(ms)} over`;
  }
  const secs = Math.max(0, Math.ceil((ui.nextResortAt - Date.now()) / 1000));
  $('#resort').textContent = `Re-ranked ${fmtClockSec(ui.board?.evaluatedAt ?? t)} · next in ${secs}s`;
  if (ui.pending) {
    const left = Math.max(0, Math.ceil((ui.pending.deadline - Date.now()) / 1000));
    const el = $('#undoCount');
    if (el) el.textContent = left;
  }
}

function ticketView({ order, ev, rank }, lane) {
  const rows = kitchen.checklist(order.id);
  const progress = kitchen.progress(order.id);
  const expanded = ui.expanded.has(order.id);
  const closed = !['new', 'in_progress'].includes(order.status);
  const compact = !expanded && (isRush() || lane === 'done' || lane === 'ready');
  const upd = order.updated && !order.updated.acknowledgedAt ? order.updated : null;
  const highlight = new Set(upd?.highlightKeys ?? []);
  const changedItems = new Set((upd?.changes ?? []).filter((c) => c.target === 'item' && c.kind !== 'removed').map((c) => c.itemId));
  const pendingKeys = ui.pending?.orderId === order.id ? new Set(ui.pending.keys) : new Set();
  const plat = PLATFORMS[order.platform]?.label ?? order.platform;

  const className = ['ticket', `lvl-${ev.level}`, compact ? 'compact' : '', expanded ? 'expanded' : '', closed ? 'closed' : '', ev.cooking ? 'cooking' : ''].filter(Boolean).join(' ');

  const strip = `<div class="strip">${icon(ev.level)}<span>${esc(ev.label)}</span>
    ${ev.cooking ? '<span class="cooking-tag">Cooking</span>' : ''}
    ${rank ? `<span class="rank">#${rank} to start</span>` : ''}
    ${['completed', 'cancelled'].includes(order.status) ? '' : `<span class="due" data-due="${ev.promisedAt}"></span>`}</div>`;

  const head = `<button class="t-head" type="button" data-action="toggle" aria-expanded="${expanded}" aria-label="Order ${esc(order.number)}, ${esc(ev.label)}. ${expanded ? 'Collapse' : 'Expand'} details">
    <span class="t-num">#${esc(order.number)}</span>
    <span class="badge plat-${esc(order.platform)}">${esc(plat)}</span>
    ${order.customer ? `<span class="customer">${esc(order.customer)}</span>` : ''}
    <span class="status-chip">${esc(STATUS_LABEL[order.status])}</span></button>`;

  let banners = '';
  if (order.status === 'cancelled' && !order.cancelAcknowledgedAt) {
    banners += `<div class="banner cancel"><div class="row">${icon('cancelled')} CANCELLED — STOP PREP
      <button class="btn small" type="button" data-action="ack-cancel">Acknowledge</button></div>
      <div>${esc(order.cancelReason ?? '')}</div></div>`;
  }
  if (upd) {
    banners += `<div class="banner updated"><div class="row">${icon('updated')} UPDATED ${esc(fmtClock(upd.at))} · ${upd.changes.length} change${upd.changes.length === 1 ? '' : 's'}
      <button class="btn small" type="button" data-action="ack-update">Seen</button></div>
      <ul>${upd.changes.map((c) => `<li>${esc(describeChange(c))}</li>`).join('')}</ul></div>`;
  }
  if (order.override) {
    banners += `<div class="banner override">OVERRIDE by ${esc(shortName(order.override.by))} at ${esc(fmtClock(order.override.at))} — “${esc(order.override.reason)}”
      ${order.override.unconfirmed.length ? `<br>Skipped: ${order.override.unconfirmed.map((u) => esc(u.text)).join('; ')}` : ''}</div>`;
  }

  const allergyRows = rows.filter((r) => r.type === 'allergy');
  const allergies = allergyRows.length
    ? `<div class="allergies">${allergyRows.map((r) => allergyRowHTML(r, highlight, pendingKeys)).join('')}</div>`
    : '';

  const reason = `<p class="reason">${esc(ev.reason)}</p>${ev.promisedEstimated
    ? `<p class="est-note">No promised time from ${esc(plat)}; using ${ev.slaMin}-min default.</p>` : ''}`;

  const meta = `<div class="meta">
    <span>Received <b>${esc(fmtClock(order.receivedAt))}</b></span>
    <span>Due <b>${esc(fmtClock(ev.promisedAt))}</b>${ev.promisedEstimated ? ' (est.)' : ''}</span>
    <span>Prep <b>${ev.prepMin} min</b></span>
    ${order.status === 'new' ? `<span>Start by <b>${esc(fmtClock(ev.latestStartAt))}</b></span>` : ''}
    ${order.startedAt ? `<span>Started <b>${esc(fmtClock(order.startedAt))}</b></span>` : ''}</div>`;

  const planById = new Map(ev.plan.items.map((p) => [p.itemId, p]));
  const items = `<ul class="items">${order.items.map((item) => {
    const p = planById.get(item.id);
    const itemAllergy = allergyRows.filter((a) => a.itemId === item.id);
    const mods = rows.filter((r) => r.type === 'modifier' && r.itemId === item.id);
    const stagger = order.status === 'new' && order.items.length > 1 && p.startOffsetMin >= 1 ? `<span class="stagger-chip">start +${Math.round(p.startOffsetMin)}m</span>` : '';
    return `<li class="item ${changedItems.has(item.id) ? 'changed-item' : ''}">
      <div class="item-head"><span class="qty">${item.qty}×</span><span class="item-name">${esc(item.name)}</span>
        ${itemAllergy.map((a) => `<span class="item-allergy">${icon('allergy')}${esc(a.allergen)}</span>`).join('')}
        ${stagger}<span class="item-prep">${p.unitPrepMin} min · ${esc(p.stationLabel)}</span></div>
      ${mods.length ? `<ul class="mods">${mods.map((r) => modRowHTML(r, highlight, pendingKeys)).join('')}</ul>` : ''}
    </li>`;
  }).join('')}</ul>`;

  const pct = progress.total ? Math.round((progress.confirmed / progress.total) * 100) : 100;
  const progressHTML = progress.total
    ? `<div class="progress ${progress.confirmed < progress.total ? 'incomplete' : ''}">
        <span class="label">${progress.confirmed < progress.total ? '' : icon('check')}${progress.confirmed} of ${progress.total} confirmed</span>
        ${progress.pendingAllergies ? `<span class="a-pending">${icon('allergy')} ${progress.pendingAllergies} allergy</span>` : ''}
        <span class="track"><span class="fill" style="width:${pct}%"></span></span></div>`
    : '<div class="progress"><span class="label muted">No modifiers</span></div>';

  let details = '';
  if (expanded) {
    const log = kitchen.orderLog(order.id).slice(-8).reverse();
    details = `<div class="details">
      ${ev.stagger && order.status === 'new' ? `<div class="stagger">${esc(ev.stagger)}</div>` : ''}
      <h4>Why this rank</h4>
      <div>Latest safe start = due ${esc(fmtClock(ev.promisedAt))} − prep ${ev.prepMin} min − buffer ${ev.bufferMin} min = <b>${esc(fmtClock(ev.latestStartAt))}</b>.
        Slack now: <b>${ev.slackMin >= 0 ? `${Math.floor(ev.slackMin)} min` : `${Math.ceil(-ev.slackMin)} min behind`}</b>.</div>
      ${ev.plan.stations.map((s) => `<div>${esc(s.label)}: ${s.unitCount} unit${s.unitCount > 1 ? 's' : ''}, ${s.capacity} at a time → ${s.makespanMin} min${s.shared ? ' (shared, queued)' : ''}</div>`).join('')}
      <h4>Ticket history</h4>
      <ol>${log.map((e) => `<li>${esc(fmtClockSec(e.at))} — ${esc(auditLabel(e))}${e.employeeId ? ` · ${esc(shortName(e.employeeId))}` : ''}${e.text ? ` · ${esc(e.text)}` : ''}</li>`).join('')}</ol>
    </div>`;
  }

  const actions = actionsHTML(order, expanded);
  const html = `${strip}${head}${banners}${allergies}${reason}${meta}${items}${progressHTML}${details}${actions}`;
  return { html, className };
}

function whoLine(c) {
  if (!c) return 'Needs confirmation';
  return `Confirmed by ${shortName(c.employeeId)} · ${c.method} · ${fmtClock(c.at)}`;
}

function checkbox(r, pendingKeys, extraLabel) {
  const c = r.confirmation;
  const pend = pendingKeys.has(r.key);
  const initials = c ? EMPLOYEES.find((e) => e.id === c.employeeId)?.initials ?? '✓' : pend ? '…' : '';
  const state = c ? 'Confirmed' : pend ? 'Confirming' : 'Needs confirmation';
  return `<button class="chk ${c ? 'on' : ''} ${pend ? 'pend' : ''}" type="button" role="checkbox" aria-checked="${!!c}"
    data-action="check" data-key="${esc(r.key)}" aria-label="${esc(extraLabel)}: ${esc(r.text)}. ${state}">${esc(initials)}</button>`;
}

function allergyRowHTML(r, highlight, pendingKeys) {
  const c = r.confirmation;
  const note = r.text.includes('—') ? r.text.split('—').slice(1).join('—').trim() : '';
  return `<div class="allergy-row ${c ? 'confirmed' : ''}">
    ${checkbox(r, pendingKeys, 'Allergy')}
    <div class="a-text">
      <div class="a-title">${icon('allergy')} ${esc(r.allergen)} allergy${r.severity === 'severe' ? ' · SEVERE' : ''}${highlight.has(r.key) ? '<span class="chg">CHANGED</span>' : ''}</div>
      <div class="a-note">${esc(r.itemId ? `→ ${r.itemName}` : 'Whole order')}${note ? ` · ${esc(note)}` : ''}</div>
      <div class="who">${esc(whoLine(c))}</div>
    </div></div>`;
}

function modRowHTML(r, highlight, pendingKeys) {
  const c = r.confirmation;
  const pend = pendingKeys.has(r.key);
  return `<li class="check-row ${c ? 'confirmed' : 'unconfirmed'}">
    ${checkbox(r, pendingKeys, r.itemName)}
    <span class="m-body"><span class="m-text">${esc(r.text)}${highlight.has(r.key) ? '<span class="chg">CHANGED</span>' : ''}</span>
    <span class="who">${esc(pend ? 'Confirming…' : whoLine(c))}</span></span></li>`;
}

function actionsHTML(order, expanded) {
  const back = expanded && ['in_progress', 'ready'].includes(order.status)
    ? `<button class="btn small ghost" type="button" data-action="back">${icon('back')} Back to ${order.status === 'ready' ? 'In Progress' : 'New'}</button>` : '';
  switch (order.status) {
    case 'new':
      return `<div class="actions"><button class="btn big go" type="button" data-action="advance">${icon('play')} Start</button></div>`;
    case 'in_progress': {
      const blocked = kitchen.readyBlockReason(order.id);
      return `<div class="actions">
        <button class="btn big primary" type="button" data-action="advance" ${blocked ? 'aria-disabled="true"' : ''}>${icon('ready')} Mark Ready</button>
        ${blocked ? `<button class="btn small ghost" type="button" data-action="override">Manager override</button>` : ''}
        ${back}
        ${blocked ? `<div class="blocked">${icon('lock')} ${esc(blocked)}</div>` : ''}</div>`;
    }
    case 'ready':
      return `<div class="actions"><button class="btn big go" type="button" data-action="advance">${icon('check')} Complete</button>${back}</div>`;
    default:
      return '';
  }
}

// ---------- feedback ----------
function toast(message, kind = 'info', ms = 4200) {
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.textContent = message;
  $('#toasts').appendChild(el);
  while ($('#toasts').children.length > 4) $('#toasts').firstChild.remove();
  setTimeout(() => el.remove(), ms);
}
function say(text) { speak(text, { enabled: ui.sound }); }
function feedback(message, kind) { toast(message, kind); say(message); }

function showTranscript(text, mode) {
  const el = $('#transcript');
  el.classList.toggle('interim', mode === 'interim');
  el.innerHTML = `<span class="lbl">${mode === 'interim' ? 'Hearing' : mode === 'typed' ? 'Typed' : 'Heard'}</span>${esc(text)}`;
}

// ---------- confirmations ----------
function requireEmployee(retry) {
  if (ui.employeeId) return true;
  ui.afterLogin = retry;
  toast('Sign in first so confirmations have your name.', 'warn');
  openLogin();
  return false;
}

function handleCheck(orderId, key) {
  if (!requireEmployee(() => handleCheck(orderId, key))) return;
  const order = kitchen.getOrder(orderId);
  if (!['new', 'in_progress'].includes(order.status)) {
    toast(`Order #${order.number} is ${STATUS_LABEL[order.status]}; confirmations are locked.`, 'warn');
    return;
  }
  if (ui.pending?.orderId === orderId && ui.pending.keys.includes(key)) { undoPending(); return; }
  const row = kitchen.checklist(orderId).find((r) => r.key === key);
  if (!row) return;
  if (row.confirmation) {
    const r = kitchen.undoConfirmation(orderId, key, { employeeId: ui.employeeId, reason: 'unchecked by tap' });
    if (r.ok) toast(`Unchecked “${row.text}” on #${order.number} (logged).`, 'warn');
    return;
  }
  if (row.type === 'allergy') {
    openAllergyConfirm({ orderId, key, method: 'tap', transcript: null });
    return;
  }
  const r = kitchen.confirm(orderId, key, { employeeId: ui.employeeId, method: 'tap' });
  if (!r.ok) toast(r.message, 'error');
}

function startPending({ orderId, keys, transcript, method, heard, note }) {
  if (ui.pending) commitPending();
  const ms = config.undoWindowSec * 1000;
  ui.pending = { orderId, keys, transcript, method, heard, employeeId: ui.employeeId, deadline: Date.now() + ms, timer: setTimeout(commitPending, ms) };
  const el = $('#pending');
  el.hidden = false;
  el.innerHTML = `<span class="heard">${icon('check')} ${esc(heard)} ✓</span>
    <button class="btn warn" type="button" id="undoPending">Undo (<span id="undoCount">${config.undoWindowSec}</span>)</button>
    ${note ? `<span class="note">${icon('allergy')} ${esc(note)}</span>` : ''}
    <span class="bar" style="animation-duration:${ms}ms"></span>`;
  $('#undoPending').addEventListener('click', undoPending);
  say(`${heard.replace(/–/g, ',')}.${note ? ` ${note}` : ''}`);
  renderBoard();
}

function commitPending() {
  const p = ui.pending;
  if (!p) return;
  clearTimeout(p.timer);
  ui.pending = null;
  $('#pending').hidden = true;
  const results = p.keys.map((key) => kitchen.confirm(p.orderId, key, { employeeId: p.employeeId, method: p.method, transcript: p.transcript }));
  const ok = results.filter((r) => r.ok).length;
  const failed = results.filter((r) => !r.ok);
  if (ok) toast(`Confirmed by ${shortName(p.employeeId)}: ${p.heard}`, 'success', 2600);
  for (const f of failed) toast(f.message, 'error');
  renderBoard();
}

function undoPending() { cancelPending(true); }
function cancelPending(logIt) {
  const p = ui.pending;
  if (!p) return;
  clearTimeout(p.timer);
  ui.pending = null;
  $('#pending').hidden = true;
  if (logIt) {
    kitchen.logVoiceCancelled({ transcript: p.transcript, orderId: p.orderId, keys: p.keys, employeeId: p.employeeId, method: p.method });
    feedback('Undone. Nothing was checked.', 'warn');
  }
}

// ---------- voice / typed commands ----------
function handleCommand(text, method) {
  showTranscript(text, method === 'typed' ? 'typed' : 'final');
  if (!ui.employeeId) {
    kitchen.logVoiceRejection({ transcript: text, code: 'no_employee', message: 'No employee signed in', method });
    requireEmployee(() => handleCommand(text, method));
    return;
  }
  if (ui.allergyPending) {
    if (isReadBackConfirmation(text)) { commitAllergy(method, text); return; }
    closeAllergy(false);
  }
  const r = interpretVoiceCommand(text, kitchen.voiceContext());
  if (!r.ok) {
    kitchen.logVoiceRejection({ transcript: text, code: r.code, message: r.message, orderId: r.orderId ?? null, employeeId: ui.employeeId, method });
    if (r.kind === 'ambiguous') openAmbiguity(r, method, text);
    feedback(r.message, r.kind === 'ambiguous' ? 'warn' : 'error');
    return;
  }
  if (r.requiresSecondStep) {
    openAllergyConfirm({ orderId: r.order.id, key: r.target.key, method, transcript: text, heard: r.heard });
    return;
  }
  startPending({ orderId: r.order.id, keys: r.targets.map((t) => t.key), transcript: text, method, heard: r.heard, note: r.message });
}

function openAmbiguity(r, method, transcript) {
  const dlg = $('#ambiguityDialog');
  $('#ambiguityTitle').textContent = r.message;
  const box = $('#ambiguityChoices');
  box.innerHTML = r.candidates.map((c, i) => `<button class="btn" type="button" data-i="${i}">${c.type === 'allergy' ? icon('allergy') : ''}<b>${esc(c.itemName)}</b>&nbsp;— ${esc(c.text)}${c.confirmation ? ` (already confirmed by ${esc(shortName(c.confirmation.employeeId))})` : ''}</button>`).join('');
  box.onclick = (e) => {
    const btn = e.target.closest('button[data-i]');
    if (!btn) return;
    const c = r.candidates[Number(btn.dataset.i)];
    dlg.close();
    if (c.confirmation) { toast(`Already confirmed by ${shortName(c.confirmation.employeeId)}.`, 'warn'); return; }
    if (c.type === 'allergy') openAllergyConfirm({ orderId: r.orderId, key: c.key, method, transcript });
    else startPending({ orderId: r.orderId, keys: [c.key], transcript, method, heard: `Order ${r.orderNumber} – ${c.text} (${c.itemName}) – satisfied` });
  };
  dlg.showModal();
}

function openAllergyConfirm({ orderId, key, method, transcript, heard }) {
  const order = kitchen.getOrder(orderId);
  const row = kitchen.checklist(orderId).find((r) => r.key === key);
  if (!row) return;
  ui.allergyPending = { orderId, key, method, transcript };
  const note = row.text.includes('—') ? row.text.split('—').slice(1).join('—').trim() : '';
  $('#allergyBody').innerHTML = `<div class="allergy-big">
      <div class="a-title">${icon('allergy')} ${esc(row.allergen)} allergy${row.severity === 'severe' ? ' · SEVERE' : ''}</div>
      <p>Order #${esc(order.number)} · ${esc(row.itemId ? row.itemName : 'Whole order')}${note ? ` · ${esc(note)}` : ''}</p>
    </div>
    ${transcript ? `<p class="muted">Heard: “${esc(transcript)}”</p>` : ''}
    <p><b>Step 2 of 2:</b> confirm this allergy request has been handled for this order${method === 'voice' ? ', or hold to talk and say “confirm”' : ''}.</p>`;
  $('#allergyPtt').hidden = !(method === 'voice' && speech.supported);
  $('#allergyDialog').showModal();
  if (method === 'voice') say(`Allergy. Order ${order.number}, ${row.allergen}${row.itemId ? `, ${row.itemName}` : ', whole order'}. Say confirm, or tap confirm.`);
}

function commitAllergy(method, transcript) {
  const p = ui.allergyPending;
  if (!p) return;
  const fullTranscript = p.transcript && transcript && transcript !== p.transcript ? `${p.transcript} | ${transcript}` : p.transcript ?? transcript ?? null;
  const r = kitchen.confirm(p.orderId, p.key, { employeeId: ui.employeeId, method: p.method, transcript: fullTranscript });
  closeAllergy(false);
  if (r.ok) feedback(`Allergy confirmed by ${shortName(ui.employeeId)}`, 'success');
  else feedback(r.message, 'error');
}

function closeAllergy(logIt) {
  const p = ui.allergyPending;
  ui.allergyPending = null;
  if ($('#allergyDialog').open) $('#allergyDialog').close();
  if (logIt && p?.transcript) kitchen.logVoiceCancelled({ transcript: p.transcript, orderId: p.orderId, keys: [p.key], employeeId: ui.employeeId, method: p.method });
}

// ---------- status ----------
function handleAdvance(orderId) {
  const order = kitchen.getOrder(orderId);
  if (order.status === 'in_progress') {
    const reason = kitchen.readyBlockReason(orderId);
    if (reason) {
      kitchen.advance(orderId, { employeeId: ui.employeeId }); // logs ready_blocked
      toast(`Can't mark #${order.number} Ready: ${reason}. Confirm them, or use manager override.`, 'error');
      return;
    }
  }
  const r = kitchen.advance(orderId, { employeeId: ui.employeeId });
  if (!r.ok) toast(r.message, 'error');
}

function openOverride(orderId) {
  const order = kitchen.getOrder(orderId);
  const pending = kitchen.checklist(orderId).filter((r) => !r.confirmation);
  $('#overrideTitle').textContent = `Manager override · #${order.number}`;
  $('#overrideList').innerHTML = pending.map((r) => `<li>${r.type === 'allergy' ? 'ALLERGY: ' : ''}${esc(r.itemName)} — ${esc(r.text)}</li>`).join('');
  const managers = EMPLOYEES.filter((e) => e.role === 'manager');
  $('#overrideManager').innerHTML = managers.map((m) => `<option value="${m.id}">${esc(m.name)}</option>`).join('');
  if (managers.some((m) => m.id === ui.employeeId)) $('#overrideManager').value = ui.employeeId;
  $('#overridePin').value = '';
  $('#overrideReason').value = '';
  $('#overrideError').textContent = '';
  $('#overrideForm').onsubmit = (e) => {
    e.preventDefault();
    const r = kitchen.overrideReady(orderId, { managerId: $('#overrideManager').value, pin: $('#overridePin').value, reason: $('#overrideReason').value });
    if (!r.ok) { $('#overrideError').textContent = r.message; return; }
    $('#overrideDialog').close();
    toast(`#${order.number} marked Ready by manager override (flagged).`, 'warn');
  };
  $('#overrideDialog').showModal();
}

// ---------- sign in ----------
let loginChoice = null;
function openLogin() {
  loginChoice = ui.employeeId;
  $('#empGrid').innerHTML = EMPLOYEES.map((e) => `<button type="button" class="emp" role="radio" aria-checked="${e.id === loginChoice}" data-id="${e.id}">
    <b>${esc(e.name)}</b><span class="role">${esc(e.role)} · PIN ${esc(e.pin)} (demo)</span></button>`).join('');
  $('#loginPin').value = '';
  $('#loginError').textContent = '';
  $('#signOutBtn').hidden = !ui.employeeId;
  $('#loginDialog').showModal();
}
function setEmployee(id) {
  ui.employeeId = id;
  storage.set('kds.employee', id);
  renderHeader();
}

// ---------- audit log ----------
const AUDIT_LABELS = {
  order_received: 'Order received', confirm: 'Confirmed', confirm_ignored: 'Duplicate confirmation ignored', confirm_rejected: 'Confirmation rejected',
  undo: 'Confirmation undone', status: 'Status', ready_blocked: 'Ready blocked', override: 'MANAGER OVERRIDE', override_rejected: 'Override rejected',
  order_updated: 'ORDER UPDATED', confirmation_reset: 'Confirmation reset', confirmation_removed: 'Confirmation removed', cancelled: 'ORDER CANCELLED',
  acknowledged: 'Acknowledged', voice_rejected: 'Voice command rejected', voice_cancelled: 'Voice confirmation undone (undo window)',
};
const auditLabel = (e) => `${AUDIT_LABELS[e.type] ?? e.type}${e.type === 'status' || e.type === 'ready_blocked' ? `: ${e.detail}` : ''}`;
const AUDIT_FILTERS = {
  all: () => true,
  confirm: (e) => ['confirm', 'confirm_ignored', 'undo', 'confirm_rejected', 'voice_cancelled'].includes(e.type),
  flags: (e) => e.flagged || ['confirmation_reset', 'confirmation_removed', 'cancelled', 'ready_blocked', 'override_rejected'].includes(e.type),
  voice: (e) => e.type === 'voice_rejected',
};
function renderAudit() {
  const filter = AUDIT_FILTERS[$('#auditFilter').value] ?? AUDIT_FILTERS.all;
  const rows = kitchen.auditLog.filter(filter).slice().reverse();
  $('#auditBody').innerHTML = rows.map((e) => {
    const o = e.orderId ? kitchen.getOrder(e.orderId) : null;
    const detail = [e.transcript ? `“${e.transcript}”` : '', e.type === 'status' ? '' : e.detail ?? ''].filter(Boolean).join(' — ');
    return `<tr class="${e.flagged ? 'flagged' : ''}"><td class="mono">${esc(fmtClockSec(e.at))}</td><td>${esc(auditLabel(e))}</td>
      <td>${o ? `#${esc(o.number)}` : ''}</td><td>${esc(e.text ?? '')}</td><td>${e.employeeId ? esc(shortName(e.employeeId)) : ''}</td>
      <td>${esc(e.method ?? '')}</td><td>${esc(detail)}</td></tr>`;
  }).join('') || '<tr><td colspan="7" class="muted">No entries.</td></tr>';
}

// ---------- demo tools ----------
const DEMO_ACTIONS = [
  { label: 'Advance clock +5 min', hint: 'Watch tickets re-rank and escalate', run: () => { clockOffset += 5 * MIN; renderBoard(); } },
  { label: 'Reset clock to now', run: () => { clockOffset = 0; renderBoard(); } },
  { label: 'Customer edits #42 on DoorDash', hint: '"extra pickles" → "no pickles", + "no cheese"', run: () => { const r = demoUpdateOrder42(kitchen); if (!r.ok) toast(r.message, 'warn'); else toast('#42 UPDATED — affected confirmations reset.', 'warn'); } },
  { label: 'Cancel #44', hint: 'Shows CANCELLED banner until acknowledged', run: () => { const r = kitchen.cancelOrder('o44', { reason: 'Customer cancelled on DoorDash' }); if (!r.ok) toast(r.message, 'warn'); } },
  { label: 'Start a rush (+8 orders)', hint: 'Auto rush mode switches to compact tickets', run: () => { for (const o of createRushOrders(now())) kitchen.addOrder(o); toast('8 new orders received.', 'info'); } },
  { label: 'Two cooks confirm the same item', hint: 'First wins; second is ignored and logged', run: simulateDoubleConfirm },
  { label: 'Reset demo', run: () => { clockOffset = 0; boot(); toast('Demo reset.', 'info'); } },
];
const DEMO_COMMANDS = [
  ['Order 42, no onions satisfied', 'Ambiguous: two items have it'],
  ['Order 42, chicken sandwich no onions satisfied', 'Item name resolves it'],
  ['Order 42, all modifiers satisfied', 'Bulk: modifiers only, never allergies'],
  ['Order 42, sesame allergy satisfied', 'Allergy: needs a second step'],
  ['Order 42, light salt satisfied', 'Already confirmed'],
  ['Order 43, sauce on the side satisfied', 'Fuzzy match after an update'],
  ['Order 46, extra basil satisfied', 'Simple confirm with undo window'],
  ['Order 39, honey mustard on side satisfied', 'Rejected: order already Ready'],
  ['Order 99, no onions satisfied', 'Rejected: unknown order'],
  ['Order 45, extra mayo satisfied', 'Rejected: no such modifier'],
];

function simulateDoubleConfirm() {
  const target = [...ui.board.inProgress, ...ui.board.queue]
    .map((e) => ({ order: e.order, row: kitchen.checklist(e.order.id).find((r) => r.type === 'modifier' && !r.confirmation) }))
    .find((x) => x.row);
  if (!target) { toast('No unconfirmed modifiers to demo with.', 'warn'); return; }
  const a = ui.employeeId ?? 'e-maria';
  const b = EMPLOYEES.find((e) => e.id !== a && e.role === 'cook')?.id ?? 'e-dev';
  const r1 = kitchen.confirm(target.order.id, target.row.key, { employeeId: a, method: 'tap' });
  const r2 = kitchen.confirm(target.order.id, target.row.key, { employeeId: b, method: 'voice', transcript: `Order ${target.order.number}, ${target.row.text} satisfied` });
  toast(`#${target.order.number} “${target.row.text}”: ${shortName(a)} ${r1.ok ? 'confirmed first' : 'failed'}; ${shortName(b)} ${r2.ok ? 'ALSO confirmed (bug!)' : 'ignored and logged'}.`, r2.ok ? 'error' : 'success', 6000);
}

function renderDemo() {
  $('#demoActions').innerHTML = DEMO_ACTIONS.map((a, i) => `<button class="btn" type="button" data-i="${i}">${esc(a.label)}${a.hint ? `<small>${esc(a.hint)}</small>` : ''}</button>`).join('');
  $('#demoCommands').innerHTML = DEMO_COMMANDS.map(([cmd, hint], i) => `<button class="btn" type="button" data-cmd="${i}">“${esc(cmd)}”<small>${esc(hint)}</small></button>`).join('');
}

// ---------- events ----------
function bindEvents() {
  $('#board').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    const ticket = btn.closest('.ticket');
    const orderId = ticket?.dataset.id;
    if (!orderId) return;
    switch (btn.dataset.action) {
      case 'toggle':
        ui.expanded.has(orderId) ? ui.expanded.delete(orderId) : ui.expanded.add(orderId);
        renderBoard();
        break;
      case 'check': handleCheck(orderId, btn.dataset.key); break;
      case 'advance': handleAdvance(orderId); break;
      case 'back': { const r = kitchen.stepBack(orderId, { employeeId: ui.employeeId }); if (!r.ok) toast(r.message, 'error'); break; }
      case 'override': openOverride(orderId); break;
      case 'ack-update':
      case 'ack-cancel': {
        const what = btn.dataset.action === 'ack-update' ? 'update' : 'cancel';
        if (!requireEmployee(() => kitchen.acknowledge(orderId, what, { employeeId: ui.employeeId }))) break;
        kitchen.acknowledge(orderId, what, { employeeId: ui.employeeId });
        break;
      }
      default: break;
    }
  });

  // Push-to-talk: pointer hold or Space bar hold.
  speech = createSpeechInput({
    onInterim: (t) => showTranscript(t, 'interim'),
    onFinal: (t) => handleCommand(t, 'voice'),
    onError: (err) => {
      if (err === 'no-speech' || err === 'aborted') return;
      feedback(err === 'not-allowed' ? 'Microphone blocked. Allow mic access, or use the typed command box.' : `Voice error: ${err}. Use tap or typed command.`, 'error');
    },
    onStateChange: (on) => {
      $('#ptt').classList.toggle('listening', on);
      $('#allergyPtt').classList.toggle('listening', on);
      $('.ptt-label').textContent = on ? 'Listening… release to send' : 'Hold to talk';
      if (on) showTranscript('…', 'interim');
    },
  });
  const ptt = $('#ptt');
  for (const el of document.querySelectorAll('.ptt-icon')) el.innerHTML = icon('mic');
  const allergyPtt = $('#allergyPtt');
  allergyPtt.addEventListener('pointerdown', (e) => { e.preventDefault(); allergyPtt.setPointerCapture?.(e.pointerId); speech.start(); });
  for (const ev of ['pointerup', 'pointercancel']) allergyPtt.addEventListener(ev, () => speech.stop());
  if (!speech.supported) {
    ptt.disabled = true;
    $('.ptt-label').textContent = 'Voice unavailable';
    $('#pttHint').textContent = 'This browser has no Web Speech API (try Chrome, Edge or Safari). Use the typed box; it runs the same parser.';
  }
  ptt.addEventListener('pointerdown', (e) => { e.preventDefault(); ptt.setPointerCapture?.(e.pointerId); speech.start(); });
  for (const ev of ['pointerup', 'pointercancel']) ptt.addEventListener(ev, () => speech.stop());
  ptt.addEventListener('contextmenu', (e) => e.preventDefault());
  let spaceDown = false;
  // Space works on the board, and inside the allergy dialog for the spoken "confirm" read-back.
  const typingTarget = (el) => el && (el.matches('input, textarea, select') || (el.closest('dialog[open]') && !el.closest('#allergyDialog')));
  addEventListener('keydown', (e) => {
    if (e.code !== 'Space' || e.repeat || typingTarget(document.activeElement) || !speech.supported) return;
    e.preventDefault();
    spaceDown = true;
    speech.start();
  });
  addEventListener('keyup', (e) => {
    if (e.code === 'Space' && spaceDown) { spaceDown = false; e.preventDefault(); speech.stop(); }
  });

  $('#typedForm').addEventListener('submit', (e) => {
    e.preventDefault();
    const text = $('#typedInput').value.trim();
    if (!text) return;
    $('#typedInput').value = '';
    handleCommand(text, 'typed');
  });

  $('#rushToggle').addEventListener('click', () => {
    ui.rushMode = { auto: 'on', on: 'off', off: 'auto' }[ui.rushMode];
    storage.set('kds.rush', ui.rushMode);
    renderBoard();
  });
  $('#soundToggle').addEventListener('click', () => {
    ui.sound = !ui.sound;
    storage.set('kds.sound', ui.sound ? 'on' : 'off');
    renderHeader();
    if (ui.sound) say('Sound on.');
  });

  // Sign in
  $('#employeeBtn').addEventListener('click', openLogin);
  $('#empGrid').addEventListener('click', (e) => {
    const b = e.target.closest('.emp');
    if (!b) return;
    loginChoice = b.dataset.id;
    for (const x of $('#empGrid').children) x.setAttribute('aria-checked', String(x.dataset.id === loginChoice));
    $('#loginPin').focus();
  });
  $('#loginForm').addEventListener('submit', (e) => {
    if (e.submitter?.value === 'cancel') { ui.afterLogin = null; return; }
    e.preventDefault();
    const emp = EMPLOYEES.find((x) => x.id === loginChoice);
    if (!emp) { $('#loginError').textContent = 'Pick your name.'; return; }
    if ($('#loginPin').value !== emp.pin) { $('#loginError').textContent = 'Wrong PIN.'; return; }
    setEmployee(emp.id);
    $('#loginDialog').close();
    toast(`Signed in: ${emp.name}`, 'success', 2000);
    const next = ui.afterLogin;
    ui.afterLogin = null;
    next?.();
  });
  $('#signOutBtn').addEventListener('click', () => { setEmployee(null); $('#loginDialog').close(); toast('Signed out.', 'info', 2000); });

  // Allergy step 2
  $('#allergyConfirm').addEventListener('click', () => commitAllergy('tap', null));
  $('#allergyCancel').addEventListener('click', () => { closeAllergy(true); toast('Allergy not confirmed. Nothing changed.', 'warn'); });
  $('#allergyDialog').addEventListener('cancel', () => closeAllergy(true));

  $('#ambiguityCancel').addEventListener('click', () => $('#ambiguityDialog').close());
  $('#overrideCancel').addEventListener('click', () => $('#overrideDialog').close());

  $('#auditBtn').addEventListener('click', () => { renderAudit(); $('#auditDialog').showModal(); });
  $('#auditFilter').addEventListener('change', renderAudit);
  $('#auditClose').addEventListener('click', () => $('#auditDialog').close());

  $('#demoBtn').addEventListener('click', () => { renderDemo(); $('#demoDialog').showModal(); });
  $('#demoClose').addEventListener('click', () => $('#demoDialog').close());
  $('#demoActions').addEventListener('click', (e) => {
    const b = e.target.closest('[data-i]');
    if (!b) return;
    DEMO_ACTIONS[Number(b.dataset.i)].run();
    $('#demoDialog').close();
  });
  $('#demoCommands').addEventListener('click', (e) => {
    const b = e.target.closest('[data-cmd]');
    if (!b) return;
    $('#demoDialog').close();
    handleCommand(DEMO_COMMANDS[Number(b.dataset.cmd)][0], 'typed');
  });
}

bindEvents();
boot();
setInterval(tick, 1000);
setInterval(renderBoard, config.refreshSec * 1000);
if (!ui.employeeId) openLogin();
