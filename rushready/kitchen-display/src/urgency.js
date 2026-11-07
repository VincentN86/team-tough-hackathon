// Urgency calculation: rank orders by latest safe START time, not arrival time.
//
//   orderPrep   = longest station schedule (units on a shared station queue for its capacity)
//   latestStart = promisedAt - orderPrep - buffer
//   slack       = latestStart - now
//   Late < 0 <= Start Now <= 3 < Start Soon <= 10 < On Track
//
// Pure functions: everything depends only on (orders, now, config).

import { DEFAULT_CONFIG, MIN, STATUS } from './config.js';

export const LEVELS = {
  late: { label: 'Late', rank: 0 },
  start_now: { label: 'Start Now', rank: 1 },
  start_soon: { label: 'Start Soon', rank: 2 },
  on_track: { label: 'On Track', rank: 3 },
  ready: { label: 'Ready', rank: 4 },
  completed: { label: 'Completed', rank: 5 },
  cancelled: { label: 'Cancelled', rank: 6 },
};

const defaultClock = (ms) =>
  new Date(ms).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });

export function itemSpec(item, config = DEFAULT_CONFIG) {
  const menu = config.menu[item.menuKey] ?? {};
  return {
    prepMin: item.prepMin ?? menu.prepMin ?? 10,
    station: item.station ?? menu.station ?? 'unassigned',
  };
}

export function resolvePromisedAt(order, config = DEFAULT_CONFIG) {
  if (Number.isFinite(order.promisedAt)) {
    return { promisedAt: order.promisedAt, estimated: false, slaMin: null };
  }
  const slaMin = config.platforms[order.platform]?.defaultSlaMin ?? config.fallbackSlaMin;
  return { promisedAt: order.receivedAt + slaMin * MIN, estimated: true, slaMin };
}

/**
 * Build a per-station schedule for one order.
 * Each station has `capacity` parallel slots. Units are placed longest-first onto
 * the least-loaded slot (LPT). Each slot is then right-aligned so it finishes at the
 * order's overall prep time, which yields staggered start offsets so everything
 * finishes together.
 */
export function planOrderPrep(order, config = DEFAULT_CONFIG) {
  const byStation = new Map();
  for (const item of order.items) {
    const { prepMin, station } = itemSpec(item, config);
    if (!byStation.has(station)) byStation.set(station, []);
    for (let u = 0; u < item.qty; u++) {
      byStation.get(station).push({ itemId: item.id, name: item.name, durationMin: prepMin });
    }
  }

  const stations = [];
  for (const [station, units] of byStation) {
    const capacity = Math.max(1, config.stations[station]?.capacity ?? 1);
    const slots = Array.from({ length: capacity }, () => ({ load: 0, units: [] }));
    const sorted = [...units].sort((a, b) => b.durationMin - a.durationMin);
    for (const unit of sorted) {
      const slot = slots.reduce((best, s) => (s.load < best.load ? s : best), slots[0]);
      slot.units.push(unit);
      slot.load += unit.durationMin;
    }
    const makespanMin = Math.max(...slots.map((s) => s.load));
    stations.push({
      station,
      label: config.stations[station]?.label ?? station,
      capacity,
      unitCount: units.length,
      makespanMin,
      shared: units.length > capacity,
      slots,
    });
  }

  const prepMin = stations.length ? Math.max(...stations.map((s) => s.makespanMin)) : 0;

  // Right-align every slot chain to prepMin.
  const unitTimes = new Map(); // itemId -> {start, end}
  for (const st of stations) {
    for (const slot of st.slots) {
      let t = prepMin - slot.load;
      for (const unit of slot.units) {
        const cur = unitTimes.get(unit.itemId) ?? { start: Infinity, end: -Infinity };
        cur.start = Math.min(cur.start, t);
        cur.end = Math.max(cur.end, t + unit.durationMin);
        unitTimes.set(unit.itemId, cur);
        t += unit.durationMin;
      }
    }
  }

  const items = order.items.map((item) => {
    const { prepMin: unitPrepMin, station } = itemSpec(item, config);
    const times = unitTimes.get(item.id) ?? { start: 0, end: 0 };
    return {
      itemId: item.id,
      name: item.name,
      qty: item.qty,
      station,
      stationLabel: config.stations[station]?.label ?? station,
      unitPrepMin,
      startOffsetMin: times.start,
      endOffsetMin: times.end,
    };
  });

  const critical = stations.reduce((a, b) => (b.makespanMin > (a?.makespanMin ?? -1) ? b : a), null);
  return { prepMin, stations, items, critical };
}

export function classifySlack(slackMin, dueInMin, config = DEFAULT_CONFIG) {
  if (dueInMin < 0 || slackMin < 0) return 'late';
  if (slackMin <= config.startNowMaxSlackMin) return 'start_now';
  if (slackMin <= config.startSoonMaxSlackMin) return 'start_soon';
  return 'on_track';
}

function describeDriver(plan, order) {
  const st = plan.critical;
  if (!st) return 'Nothing to cook';
  const longest = plan.items
    .filter((i) => i.station === st.station)
    .sort((a, b) => b.unitPrepMin - a.unitPrepMin)[0];
  if (st.shared) {
    return `${st.unitCount} items share the ${st.label.toLowerCase()} (${st.capacity} at a time), so the order needs ${st.makespanMin} min`;
  }
  const qty = longest.qty > 1 ? `${longest.qty}× ` : '';
  return `${qty}${longest.name} takes ${plan.prepMin} min`;
}

export function staggerHint(plan, clock = null, latestStartAt = null) {
  if (plan.items.length < 2) return null;
  const late = plan.items.filter((i) => i.startOffsetMin >= 1).sort((a, b) => a.startOffsetMin - b.startOffsetMin);
  if (!late.length) return null;
  const parts = late.map((i) => {
    const at = clock && latestStartAt != null ? ` (${clock(latestStartAt + i.startOffsetMin * MIN)})` : '';
    return `${i.name} at +${Math.round(i.startOffsetMin)} min${at}`;
  });
  return `Stagger: start ${parts.join(', ')} so everything finishes together.`;
}

/** Evaluate one order at `now`. Always returns a human-readable `reason`. */
export function evaluateOrder(order, now, config = DEFAULT_CONFIG, clock = defaultClock) {
  const { promisedAt, estimated, slaMin } = resolvePromisedAt(order, config);
  const plan = planOrderPrep(order, config);
  const bufferMin = config.bufferMin;
  const latestStartAt = promisedAt - (plan.prepMin + bufferMin) * MIN;
  const slackMin = (latestStartAt - now) / MIN;
  const dueInMin = (promisedAt - now) / MIN;
  const driver = describeDriver(plan, order);
  const buf = bufferMin ? ` (+${bufferMin} min buffer)` : '';

  const base = {
    orderId: order.id,
    promisedAt,
    promisedEstimated: estimated,
    slaMin,
    prepMin: plan.prepMin,
    bufferMin,
    latestStartAt,
    slackMin,
    dueInMin,
    plan,
    stagger: staggerHint(plan, clock, latestStartAt),
  };
  const result = (level, reason, extra = {}) => ({
    ...base,
    level,
    label: LEVELS[level].label,
    reason,
    ...extra,
  });

  switch (order.status) {
    case STATUS.IN_PROGRESS: {
      const startedAt = order.startedAt ?? now;
      const expectedDoneAt = startedAt + plan.prepMin * MIN;
      const projectedSpareMin = (promisedAt - Math.max(expectedDoneAt, now)) / MIN;
      const late = dueInMin < 0 || projectedSpareMin < 0;
      const tail = dueInMin < 0
        ? `${Math.ceil(-dueInMin)} min overdue — finish and hand off ASAP.`
        : late
          ? `due ${clock(promisedAt)} — projected ${Math.ceil(-projectedSpareMin)} min late.`
          : `due ${clock(promisedAt)} (${Math.floor(projectedSpareMin)} min spare).`;
      return result(late ? 'late' : 'on_track',
        `Started ${clock(startedAt)}, est. done ${clock(expectedDoneAt)}, ${tail}`,
        { expectedDoneAt, projectedSpareMin, cooking: true });
    }
    case STATUS.READY:
      return result('ready', dueInMin < 0
        ? `Ready — pickup is ${Math.ceil(-dueInMin)} min past promised time.`
        : `Ready — waiting for pickup (due ${clock(promisedAt)}).`);
    case STATUS.COMPLETED:
      return result('completed', `Completed${order.completedAt ? ` at ${clock(order.completedAt)}` : ''} — no action needed.`);
    case STATUS.CANCELLED:
      return result('cancelled', 'Cancelled — stop prep.');
    default:
      break;
  }

  const level = classifySlack(slackMin, dueInMin, config);
  const due = Math.max(0, Math.round(dueInMin));
  let reason;
  if (level === 'late' && dueInMin < 0) {
    reason = `${driver}; order is ${Math.ceil(-dueInMin)} min overdue. Start immediately and tell front of house.`;
  } else if (level === 'late') {
    reason = `${driver}${buf}; due in ${due} min — ${Math.ceil(-slackMin)} min past the latest safe start. Start immediately.`;
  } else if (level === 'start_now') {
    const within = Math.floor(slackMin);
    reason = `${driver}${buf}; due in ${due} min. ${within > 0 ? `Start within ${within} min.` : 'Start now.'}`;
  } else if (level === 'start_soon') {
    reason = `${driver}${buf}; due in ${due} min. Start within ${Math.floor(slackMin)} min (by ${clock(latestStartAt)}).`;
  } else {
    reason = `${driver}${buf}; due in ${due} min. Start by ${clock(latestStartAt)} — ${Math.floor(slackMin)} min of slack.`;
  }
  return result(level, reason);
}

/**
 * Split and sort all orders for the board.
 * - queue (New): slack ascending, tie -> earlier receivedAt, then order number
 * - inProgress: pinned in the order they were started, so they don't shuffle
 */
export function prioritize(orders, now, config = DEFAULT_CONFIG, clock = defaultClock) {
  const evaluated = orders.map((order) => ({ order, ev: evaluateOrder(order, now, config, clock) }));
  const by = (status) => evaluated.filter((e) => e.order.status === status);

  const queue = by(STATUS.NEW).sort(
    (a, b) =>
      a.ev.slackMin - b.ev.slackMin ||
      a.order.receivedAt - b.order.receivedAt ||
      String(a.order.number).localeCompare(String(b.order.number), undefined, { numeric: true }),
  );
  queue.forEach((e, i) => (e.rank = i + 1));

  const inProgress = by(STATUS.IN_PROGRESS).sort(
    (a, b) => (a.order.startedAt ?? 0) - (b.order.startedAt ?? 0) || a.order.receivedAt - b.order.receivedAt,
  );
  const ready = by(STATUS.READY).sort((a, b) => (a.order.readyAt ?? 0) - (b.order.readyAt ?? 0));
  const completed = by(STATUS.COMPLETED).sort((a, b) => (b.order.completedAt ?? 0) - (a.order.completedAt ?? 0));
  const cancelled = by(STATUS.CANCELLED);

  return {
    queue,
    actNow: queue.filter((e) => e.ev.level === 'late' || e.ev.level === 'start_now'),
    upNext: queue.filter((e) => e.ev.level === 'start_soon' || e.ev.level === 'on_track'),
    inProgress,
    ready,
    completed,
    cancelled,
    evaluatedAt: now,
  };
}
