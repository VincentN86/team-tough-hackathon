"""STAGE 3+4 — ORDER MATCHING & IMPACT.  Owner: Feature 3 (Liz)

Deterministic: the AI never decides which orders are affected. Baseline timing comes from Vincent's
`scheduler.schedule()` (it queues items per station, shifts estimates for STATION delays and marks blocked orders), so there
is NO second scheduler here. On top of that baseline we apply ITEM-level delays the chef reported ("the pizza is 10 min late"),
which `schedule()` has no way to express. We never change an order's promised pickup_at.

Timing model (all estimates):
  baseline  = schedule()'s predicted_at (already includes station delays)
  item delay "+N min"   : extra = max(0, N - station delay already applied to that item's station)   -> never double-counted
  item delay "ready in N": item finishes at (reported time + N + packing); extra = how far that is past the baseline
  order extra = MAX over its delayed items (lines cook in parallel), revised = baseline + extra, slack = pickup - revised
  category: BLOCKED / LATE (slack<0) / AT RISK (slack<5) / ON TRACK   (same thresholds as scheduler.schedule)

Severity ladder: urgent > delayed > possible (unconfirmed only) > watch > on_track.
Edit here to change: severity rules, suggested actions, wording of server messages (_headline), thresholds.
"""
import math
from datetime import datetime, timedelta, timezone

from scheduler import PACKING_MIN, schedule
from .interpret import item_matches

RANK = {'urgent': 0, 'delayed': 1, 'possible': 2, 'watch': 3, 'on_track': 4}
RISK_SLACK_MIN = 5  # mirrors scheduler.schedule(): slack < 5 min is "at risk"


def _dt(value):
    d = datetime.fromisoformat(value)
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d


def _pending(order):
    return [it for it in order['items'] if it['status'] != 'ready']  # cooked lines can't be affected any more


def _uses(item, ing):
    terms = [t.strip().lower() for t in item['ingredients'].split(',') if t.strip()]
    return ing in terms or ing in item['name'].lower()


def _names(items):
    return ', '.join(it['name'] for it in items)


def _joined(parts):
    parts = list(dict.fromkeys(parts))
    return parts[0] if len(parts) == 1 else ', '.join(parts[:-1]) + ' and ' + parts[-1]


def _category(urgency, blocked, hard):
    if blocked:
        return 'blocked'
    if hard:
        return 'unknown'
    return {'LATE': 'late', 'RISK': 'at_risk'}.get(urgency, 'on_track')


def _headline(oid, sev, timing, causes):
    """One plain-English sentence for the server, built from the actual causes (never static text)."""
    by = lambda kind: [c for c, _, k in causes if k == kind]  # noqa: E731
    if sev == 'on_track':
        return f'Order #{oid} is on track.'
    if sev == 'possible':
        return f"Order #{oid} may be affected — {_joined([c for c, _, _ in causes])} (unconfirmed, so nothing has changed yet)."
    if by('unavailable'):
        extra = f" It is also affected because {_joined(by('delay'))}." if by('delay') else ''
        return f"Order #{oid} may require substitution or cancellation because {_joined(by('unavailable'))}.{extra}"
    if by('hard'):
        return f"Order #{oid} can't be given a ready time because {_joined(by('hard'))}."
    if sev == 'delayed':
        word = f"likely {timing['late_minutes']} min late" if timing['category'] == 'late' else f"at risk ({timing['slack']} min of slack)"
        return f"Order #{oid} is delayed and {word} because {_joined(by('delay'))}."
    if sev == 'watch' and by('delay'):
        return f"Order #{oid} remains on track even though {_joined(by('delay'))} ({timing['slack']} min of slack)."
    return f"Order #{oid}: {_joined([c for c, _, _ in causes])}."


def build_alerts(orders, incidents, flags, alert_rows=None, now=None):
    """One dict per OPEN order (packed / handed-off orders are skipped by schedule())."""
    alert_rows = alert_rows or {}
    now_dt = now or datetime.now(timezone.utc)
    active_inc = [i for i in incidents if i['active']]
    active_flags = [f for f in flags if f['active']]
    station_delay = {}
    for inc in active_inc:
        if inc['station']:
            station_delay[inc['station']] = station_delay.get(inc['station'], 0) + inc['delay_minutes']  # scheduler sums them too
    out = []
    for r in schedule(orders, incidents, now):
        reasons, causes, keys = [], [], []     # reasons: (text, certainty); causes: (short phrase, certainty, kind)
        hard = False                           # something makes an ETA impossible (down / remake)
        item_extra = 0.0
        pred, slack, urgency, late = r['predicted_at'], r['slack'], r['urgency'], r['late_minutes']

        def add(text, certainty, cause, kind, key):
            reasons.append((text, certainty))
            causes.append((cause, certainty, kind))
            keys.append(key)

        for inc in active_inc:
            if inc['ingredient']:
                hit = [it for it in _pending(r) if _uses(it, inc['ingredient'])]
                if hit:
                    add(f"{inc['ingredient'].capitalize()} unavailable — used in {_names(hit)}.", 'confirmed',
                        f"{inc['ingredient']} is unavailable", 'unavailable', f"i{inc['id']}")
            if inc['station'] and inc['delay_minutes']:
                hit = [it for it in _pending(r) if it['station'] == inc['station']]
                if hit:
                    add(f"{inc['station']} running {inc['delay_minutes']} min behind — affects {_names(hit)}.", 'confirmed',
                        f"the {inc['station'].lower()} is {inc['delay_minutes']} minutes behind", 'delay', f"i{inc['id']}")
        for f in active_flags:
            k, prov = f['kind'], f['certainty'] == 'provisional'
            tag = 'provisional' if prov else 'confirmed'
            hit = []
            if k in ('ingredient_unavailable', 'ingredient_low', 'prep_wait'):
                hit = [it for it in _pending(r) if _uses(it, f['ingredient'])]
            elif k in ('station_down', 'delay_unknown'):
                hit = [it for it in _pending(r) if it['station'] == f['station']]
            elif k == 'item_delay':
                hit = [it for it in _pending(r) if item_matches(it, f['item'])]
            key = f"f{f['id']}:{f['delay_minutes']}"
            if k == 'ingredient_unavailable' and hit:
                add(f"Possible {f['ingredient']} availability issue — kitchen confirmation needed (used in {_names(hit)}).", tag,
                    f"there may be a {f['ingredient']} availability issue", 'possible', key)
            elif k == 'ingredient_low' and hit:
                add(f"{f['ingredient'].capitalize()} running low (not confirmed unavailable) — used in {_names(hit)}.", tag,
                    f"{f['ingredient']} is running low", 'low', key)
            elif k == 'prep_wait' and hit:
                add(f"Possible {f['ingredient']} preparation delay: cooked {f['ingredient']} isn't ready yet. "
                    f"Not a confirmed shortage — used in {_names(hit)}.", tag, f"cooked {f['ingredient']} may not be ready yet", 'possible', key)
            elif k == 'delay_unknown' and hit:
                add(f"{f['station']} may be delayed (duration not reported, so no revised time) — affects {_names(hit)}.", tag,
                    f"the {f['station'].lower()} may be delayed", 'possible', key)
            elif k == 'station_down' and hit:
                add(f"{f['station']} is down (repair time unknown) — affects {_names(hit)}.", tag,
                    f"the {f['station'].lower()} is down", 'hard', key)
                hard = True
            elif k == 'order_remake' and f['order_id'] == str(r['id']):
                add(f"Chef reported order #{r['id']} needs to be remade.", tag, 'the chef reported it must be remade', 'hard', key)
                hard = True
            elif k == 'order_issue' and f['order_id'] == str(r['id']):
                add(f"Chef says {f['ingredient'] or 'an item'} may be missing from this order — check before packing.", tag,
                    f"the chef says {f['ingredient'] or 'an item'} may be missing", 'possible', key)
            elif k == 'item_delay' and hit:
                tgt = f['item']
                if prov or not f['delay_minutes']:
                    add(f"{tgt} may be late (duration not reported, so no revised time) — affects {_names(hit)}.", 'provisional',
                        f"the {tgt.lower()} may be late", 'possible', key)
                else:
                    n = f['delay_minutes']
                    if f['mode'] == 'ready_in':
                        done = _dt(f['created_at']) + timedelta(minutes=n + PACKING_MIN)
                        extra = max(0.0, (done - pred).total_seconds() / 60) if pred else 0.0
                        text = f"{tgt} will be ready in about {n} min (chef report) — affects {_names(hit)}." + ('' if extra else ' This is within the current schedule, so the estimate is unchanged.')
                        cause = f"the {tgt.lower()} won't be ready for about {n} minutes"
                    else:
                        extra = max(0.0, n - max(station_delay.get(it['station'], 0) for it in hit))  # overlap with a station delay isn't added twice
                        text = f"{tgt} running {n} min behind (chef report) — affects {_names(hit)}." + ('' if extra else ' Already covered by a station delay, so it is not counted twice.')
                        cause = f"the {tgt.lower()} is {n} minutes behind"
                    item_extra = max(item_extra, extra)
                    add(text, 'confirmed', cause, 'delay', key)
            else:
                continue

        # ---- apply item-level extra delay on top of the scheduler's baseline (never to blocked orders)
        if item_extra > 0 and pred is not None:
            pred = pred + timedelta(minutes=item_extra)
            slack = round((_dt(r['pickup_at']) - pred).total_seconds() / 60, 1)
            urgency = 'LATE' if slack < 0 else 'RISK' if slack < RISK_SLACK_MIN else 'ON TRACK'
            late = max(0, math.ceil(-slack)) if slack < 0 else 0

        confirmed = [c for _, cert, _ in causes for c in [cert] if c == 'confirmed']
        blocked = r['blocked']
        if not reasons:
            sev = 'on_track'
        elif not confirmed:
            sev = 'possible'
        elif blocked or hard:
            sev = 'urgent'
        elif urgency in ('LATE', 'RISK'):
            sev = 'delayed'
        else:
            sev = 'watch'
        timing = {'category': _category(urgency, blocked, hard), 'slack': slack, 'late_minutes': late}

        actions = []
        if sev == 'possible':
            actions.append('Heads-up only: do NOT cancel or contact the customer yet. Wait for the kitchen to confirm.')
        if blocked:
            actions.append('Contact the customer about a substitution or cancellation, and hold the order until they respond.')
        if hard:
            actions.append('Ask the chef for a repair/remake time; no revised ready time can be calculated yet.')
        if sev == 'delayed':
            actions.append('Tell staff about the delay, watch pickup timing, and prioritise this order.')
        if sev == 'watch':
            actions.append('Estimated finish still fits the promised time — keep monitoring.')
        signature = '|'.join(sorted(set(keys))) + f"|{late}|{round(item_extra)}"
        row = alert_rows.get(str(r['id']))
        out.append({
            'order': r, 'severity': sev, 'reasons': reasons,
            'headline': _headline(r['id'], sev, timing, causes),
            'actions': actions or ['Continue preparing and packing normally.'],
            'status': row['status'] if row and row['signature'] == signature else 'new',  # a changed situation re-opens the alert
            'signature': signature, 'timing': timing, 'extra_minutes': round(item_extra, 1),
            'revised_at': None if (blocked or hard or sev == 'possible') else pred,
            'promised_at': r['pickup_at'],
        })
    return sorted(out, key=lambda a: (RANK[a['severity']], a['promised_at']))


def timing_summary(alerts):
    """How many open orders can still be completed on time? {'on_track': n, 'at_risk': n, 'late': n, 'blocked': n, 'unknown': n}"""
    counts = {'on_track': 0, 'at_risk': 0, 'late': 0, 'blocked': 0, 'unknown': 0}
    for a in alerts:
        counts[a['timing']['category']] += 1
    return counts


def eta_adjustments(orders, incidents, flags):
    """INTERFACE FOR FEATURE 2 (read-only, nothing wires it yet): {order_id: extra minutes} that Feature 3's item-level
    delays add on top of scheduler.schedule()'s estimates. Feature 2 may consume this to reflect chef reports in the priority queue."""
    return {a['order']['id']: a['extra_minutes'] for a in build_alerts(orders, incidents, flags) if a['extra_minutes']}
