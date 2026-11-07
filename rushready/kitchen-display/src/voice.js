// Voice command parsing and matching. Pure functions; no browser APIs.
//
//   parseVoiceCommand("Order 42, no onions satisfied")
//     -> { ok:true, orderNumber:"42", modifierText:"no onions", isAll:false }
//   resolveVoiceCommand(parsed, { orders, confirmations, employees })
//     -> single match | bulk ("all modifiers") | ambiguity | error
//
// The app cannot see the food. A match means "a person said this is done",
// never "verified".

import { STATUS, STATUS_LABEL } from './config.js';
import { buildChecklist } from './checklist.js';

const UNITS = { zero: 0, oh: 0, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9 };
const TEENS = { ten: 10, eleven: 11, twelve: 12, thirteen: 13, fourteen: 14, fifteen: 15, sixteen: 16, seventeen: 17, eighteen: 18, nineteen: 19 };
const TENS = { twenty: 20, thirty: 30, forty: 40, fifty: 50, sixty: 60, seventy: 70, eighty: 80, ninety: 90 };
const WORD_VALUES = { ...UNITS, ...TEENS, ...TENS };

const CONFIRM_WORD = /^(satisf\w*|confirmed|done)$/;
const ALL_PATTERN = /^(all|everything)( the)?( (modifiers?|mods?|modifications?|requests?|changes|items?))?$/;
const TRAILING_FILLER = new Set(['is', 'are', 'has', 'have', 'been', 'was', 'were']);
const STOPWORDS = new Set(['the', 'a', 'an', 'on', 'of', 'with', 'please', 'and', 'for', 'to', 'in', 'item', 'its', 'it']);
// Qualifiers flip a modifier's meaning ("no onions" vs "extra onions"), so they must agree.
const QUALIFIER_SYNONYMS = {
  no: 'no', without: 'no', hold: 'no', none: 'no',
  extra: 'extra', more: 'extra', double: 'extra',
  light: 'light', easy: 'light', less: 'light',
  add: 'add', plus: 'add',
  sub: 'sub', substitute: 'sub', swap: 'sub',
  side: 'side',
};
const MATCH_THRESHOLD = 0.6;
const AMBIGUITY_MARGIN = 0.1;
const COUNT_WORDS = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten'];

export function normalizeTranscript(text) {
  return String(text ?? '')
    .toLowerCase()
    .replace(/#\s*/g, ' number ')
    .replace(/[^a-z0-9\s'-]/g, ' ')
    .replace(/['-]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Convert spoken number words to a digit string.
 * "forty two" -> "42", "four two" -> "42", "one forty two" -> "142",
 * "one hundred forty two" -> "142". Returns null if not a number.
 */
export function wordsToNumber(words) {
  const segs = [];
  for (const w of words) {
    const last = segs[segs.length - 1];
    if (/^\d+$/.test(w)) {
      segs.push({ v: Number(w), digits: w, open: null });
      continue;
    }
    if (w === 'and') continue;
    if (w === 'hundred') {
      if (!last) segs.push({ v: 100, open: 'tens' });
      else if (!last.open && last.v < 10) {
        last.v *= 100;
        last.open = 'tens';
      } else return null;
      continue;
    }
    const v = WORD_VALUES[w];
    if (v === undefined) return null;
    if (v >= 20) {
      if (last?.open === 'tens') { last.v += v; last.open = 'units'; }
      else segs.push({ v, open: 'units' });
    } else if (v >= 10) {
      if (last?.open === 'tens') { last.v += v; last.open = null; }
      else segs.push({ v, open: null });
    } else if (last?.open) {
      last.v += v;
      last.open = null;
    } else {
      segs.push({ v, open: null });
    }
  }
  if (!segs.length) return null;
  return segs.map((s) => s.digits ?? String(s.v)).join('');
}

const isNumberWord = (t) => t in WORD_VALUES || t === 'hundred';
const sameNumber = (a, b) => String(a).replace(/^0+(?=\d)/, '') === String(b).replace(/^0+(?=\d)/, '');

const fail = (code, message, extra = {}) => ({ ok: false, kind: 'error', code, message, ...extra });

/** Step 1: syntax only. "Order <number>, <modifier> satisfied". */
export function parseVoiceCommand(transcript) {
  const norm = normalizeTranscript(transcript);
  if (!norm) return fail('empty', "Didn't catch that. Nothing changed.");
  const tokens = norm.split(' ');
  const i = tokens.indexOf('order');
  if (i < 0) return fail('unrecognized', 'Say "Order [number], [modifier] satisfied". Nothing changed.');

  let j = i + 1;
  if (tokens[j] === 'number' || tokens[j] === 'num') j++;
  const numTokens = [];
  if (/^\d+$/.test(tokens[j] ?? '')) {
    while (/^\d+$/.test(tokens[j] ?? '')) numTokens.push(tokens[j++]);
  } else {
    while (j < tokens.length && (isNumberWord(tokens[j]) || (tokens[j] === 'and' && isNumberWord(tokens[j + 1] ?? '')))) {
      numTokens.push(tokens[j++]);
    }
  }
  const orderNumber = wordsToNumber(numTokens);
  if (!orderNumber) return fail('no_order_number', "Didn't hear an order number. Nothing changed.");

  const rest = tokens.slice(j);
  let kw = -1;
  for (let k = rest.length - 1; k >= 0; k--) if (CONFIRM_WORD.test(rest[k])) { kw = k; break; }
  if (kw < 0) {
    return fail('missing_keyword', `End with "satisfied", e.g. "Order ${orderNumber}, no onions satisfied". Nothing changed.`, { orderNumber });
  }
  const mod = rest.slice(0, kw);
  while (mod.length && TRAILING_FILLER.has(mod[mod.length - 1])) mod.pop();
  while (mod.length && (mod[0] === 'the' || mod[0] === 'for')) mod.shift();
  if (!mod.length) return fail('missing_modifier', `Which modifier on Order ${orderNumber}? Nothing changed.`, { orderNumber });

  const modifierText = mod.join(' ');
  return { ok: true, orderNumber, modifierText, isAll: ALL_PATTERN.test(modifierText), transcript: String(transcript) };
}

// ---------- fuzzy matching ----------

export function stem(token) {
  if (token.length > 4 && token.endsWith('ies')) return token.slice(0, -3) + 'y';
  if (token.length > 3 && token.endsWith('s') && !token.endsWith('ss')) return token.slice(0, -1);
  return token;
}

function levenshtein(a, b) {
  if (a === b) return 0;
  const prev = Array.from({ length: b.length + 1 }, (_, k) => k);
  for (let i = 1; i <= a.length; i++) {
    let diag = prev[0];
    prev[0] = i;
    for (let k = 1; k <= b.length; k++) {
      const tmp = prev[k];
      prev[k] = Math.min(prev[k] + 1, prev[k - 1] + 1, diag + (a[i - 1] === b[k - 1] ? 0 : 1));
      diag = tmp;
    }
  }
  return prev[b.length];
}

function tokenEq(a, b) {
  if (a === b) return true;
  const n = Math.min(a.length, b.length);
  if (n >= 7) return levenshtein(a, b) <= 2;
  if (n >= 4) return levenshtein(a, b) <= 1;
  return false;
}

export function matchTokens(text) {
  return normalizeTranscript(text)
    .split(' ')
    .filter((t) => t && !STOPWORDS.has(t))
    .map((t) => QUALIFIER_SYNONYMS[t] ?? stem(t));
}

/** Dice coefficient over tokens with per-token fuzzy equality. */
export function similarity(aTokens, bTokens) {
  if (!aTokens.length || !bTokens.length) return 0;
  const used = new Array(bTokens.length).fill(false);
  let hits = 0;
  for (const a of aTokens) {
    const k = bTokens.findIndex((b, idx) => !used[idx] && tokenEq(a, b));
    if (k >= 0) { used[k] = true; hits++; }
  }
  return (2 * hits) / (aTokens.length + bTokens.length);
}

const QUALIFIERS = new Set(Object.values(QUALIFIER_SYNONYMS));

function scoreCandidate(spoken, candidate, itemTokens) {
  const target = matchTokens(candidate.matchText ?? candidate.text);
  // Every qualifier on the checklist row ("no", "extra", "side"...) must be spoken.
  for (const q of target.filter((t) => QUALIFIERS.has(t))) {
    if (!spoken.includes(q)) return 0;
  }
  // Spoken qualifiers must exist on the row too ("extra sauce" never matches "no sauce").
  for (const q of spoken.filter((t) => QUALIFIERS.has(t))) {
    if (!target.includes(q) && !itemTokens.includes(q)) return 0;
  }
  const plain = similarity(spoken, target);
  // If the item name was spoken ("burger no onions"), score the remainder and add a small bonus.
  if (itemTokens.length && itemTokens.every((t) => spoken.some((s) => tokenEq(s, t)))) {
    const rest = spoken.filter((s) => !itemTokens.some((t) => tokenEq(s, t)));
    return Math.max(plain, similarity(rest, target) + 0.05);
  }
  return plain;
}

function confirmationsFor(confirmations, orderId) {
  const c = confirmations?.[orderId];
  if (!c) return {};
  return c instanceof Map ? Object.fromEntries(c) : c;
}

function employeeName(employees, id) {
  return employees?.find((e) => e.id === id)?.name ?? 'another employee';
}

const ACTIVE = new Set([STATUS.NEW, STATUS.IN_PROGRESS]);

/** Step 2: match a parsed command against live orders. Never guesses. */
export function resolveVoiceCommand(parsed, { orders = [], confirmations = {}, employees = [] } = {}) {
  if (!parsed?.ok) return parsed;
  const n = parsed.orderNumber;
  const order = orders.find((o) => sameNumber(o.number, n));
  if (!order) return fail('unknown_order', `Order ${n} not found. Nothing changed.`, { orderNumber: n });
  if (order.status === STATUS.CANCELLED) {
    return fail('order_cancelled', `Order ${n} was cancelled. Nothing changed.`, { orderNumber: n, orderId: order.id });
  }
  if (!ACTIVE.has(order.status)) {
    return fail('order_closed', `Order ${n} is already ${STATUS_LABEL[order.status]}. Nothing changed.`, { orderNumber: n, orderId: order.id });
  }

  const confs = confirmationsFor(confirmations, order.id);
  const rows = buildChecklist(order).map((r) => ({ ...r, confirmation: confs[r.key] ?? null }));

  if (parsed.isAll) {
    const targets = rows.filter((r) => r.type === 'modifier' && !r.confirmation);
    const remainingAllergies = rows.filter((r) => r.type === 'allergy' && !r.confirmation);
    if (!targets.length) {
      if (remainingAllergies.length) {
        return fail('allergy_bulk_blocked',
          `Allergies on Order ${n} must be confirmed one at a time, e.g. "Order ${n}, ${remainingAllergies[0].matchText.toLowerCase()} satisfied". Nothing changed.`,
          { orderNumber: n, orderId: order.id, remainingAllergies });
      }
      return fail('nothing_to_confirm', `Everything on Order ${n} is already confirmed.`, { orderNumber: n, orderId: order.id });
    }
    const allergyNote = remainingAllergies.length
      ? ` ${remainingAllergies.length} allergy item${remainingAllergies.length > 1 ? 's' : ''} still need${remainingAllergies.length > 1 ? '' : 's'} individual confirmation.`
      : '';
    return {
      ok: true,
      kind: 'all',
      order,
      orderNumber: n,
      targets,
      remainingAllergies,
      requiresSecondStep: false,
      heard: `Order ${n} – all ${targets.length} modifier${targets.length > 1 ? 's' : ''} – satisfied`,
      message: allergyNote.trim(),
      transcript: parsed.transcript,
    };
  }

  const spoken = matchTokens(parsed.modifierText);
  const scored = rows
    .map((r) => {
      const item = order.items.find((it) => it.id === r.itemId);
      return { row: r, score: scoreCandidate(spoken, r, item ? matchTokens(item.name) : []) };
    })
    .filter((s) => s.score >= MATCH_THRESHOLD)
    .sort((a, b) => b.score - a.score);

  if (!scored.length) {
    return fail('unknown_modifier', `Didn't find "${parsed.modifierText}" on Order ${n}. Nothing changed.`, { orderNumber: n, orderId: order.id });
  }
  const best = scored[0];
  const tied = scored.filter((s) => best.score - s.score <= AMBIGUITY_MARGIN);
  if (tied.length > 1) {
    const sameText = tied.every((s) => s.row.matchText.toLowerCase() === best.row.matchText.toLowerCase());
    const count = COUNT_WORDS[tied.length] ?? String(tied.length);
    const message = sameText
      ? `Order ${n} has ${count} '${best.row.matchText}'. Which item?`
      : `Order ${n}: "${parsed.modifierText}" could be ${tied.map((s) => `'${s.row.matchText}' (${s.row.itemName})`).join(' or ')}. Which one?`;
    return {
      ok: false,
      kind: 'ambiguous',
      code: 'ambiguous',
      orderNumber: n,
      orderId: order.id,
      candidates: tied.map((s) => s.row),
      message,
      transcript: parsed.transcript,
    };
  }

  const target = best.row;
  if (target.confirmation) {
    return fail('already_confirmed',
      `Order ${n} – ${target.matchText} was already confirmed by ${employeeName(employees, target.confirmation.employeeId)}.`,
      { orderNumber: n, orderId: order.id, target });
  }
  return {
    ok: true,
    kind: 'single',
    order,
    orderNumber: n,
    target,
    targets: [target],
    requiresSecondStep: target.type === 'allergy',
    heard: `Order ${n} – ${target.matchText}${target.itemId ? ` (${target.itemName})` : ''} – satisfied`,
    message: '',
    transcript: parsed.transcript,
  };
}

/** Convenience: parse + resolve. */
export function interpretVoiceCommand(transcript, context) {
  const parsed = parseVoiceCommand(transcript);
  if (!parsed.ok) return { ...parsed, transcript: String(transcript ?? '') };
  return resolveVoiceCommand(parsed, context);
}

/** "confirm" / "yes confirm" / "confirmed" — used for the allergy read-back step. */
export function isReadBackConfirmation(transcript) {
  return /^(yes )?(confirm(ed)?|correct|yes)( allergy)?$/.test(normalizeTranscript(transcript));
}
