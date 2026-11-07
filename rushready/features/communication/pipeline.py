"""Glue for the whole chain, UI-free so it can be unit-tested:
   utterance -> interpret (stage 2) -> publish by confidence (stage 4) -> impact (stage 3) -> a feed entry for the chef.
Owner: Feature 3 (Liz).  Edit here to change the repeat-protection window or how outcomes are summarised.
"""
import re
import time

from database import fetch_incidents, fetch_orders
from . import impact, store
from .interpret import interpret

REPEAT_WINDOW_S = 20  # the same sentence heard again within this window is ignored (speech engines repeat themselves)


def _norm(text):
    return re.sub(r'[^a-z0-9 ]', '', text.lower()).strip()


def process_utterance(text, key='', model='openrouter/auto', recent=None, now=None):
    """Handle ONE finished spoken statement (or typed report). Returns a feed entry dict:
    {text, status, via, lines[], report_id, clarify[]} where status is
    published | provisional | repeat | clarify | ignored."""
    now = time.time() if now is None else now
    entry = {'text': text.strip(), 'status': 'ignored', 'via': '', 'lines': [], 'report_id': None, 'clarify': [], 'time': now}
    if not entry['text']:
        entry['lines'] = ['Nothing heard.']
        return entry
    if recent is not None:
        for k in [k for k, t in recent.items() if now - t > REPEAT_WINDOW_S]:
            del recent[k]
        if _norm(text) in recent:
            entry.update(status='repeat', lines=['Same sentence heard again — ignored.'])
            return entry
        recent[_norm(text)] = now

    store.init_tables()
    res = interpret(text, key, model, fetch_orders())
    entry['via'] = res['via']
    if not res['issues']:
        entry['lines'] = [f'Ignored: {why}' for _, why in res['ignored']] or ['Ignored: no operational issue.']
        return entry

    outcomes, undo = store.publish(text, res['issues'])
    changed = [o for o in outcomes if o['outcome'] in store.CHANGED]
    entry['clarify'] = [o for o in outcomes if o['outcome'] == 'clarify']
    label = {'published': 'PUBLISHED to Server view', 'updated': 'UPDATED (replaced earlier number, not added)',
             'provisional': 'POSSIBLE issue sent as advisory (not confirmed)', 'resolved': 'RESOLVED',
             'duplicate': 'already reported — not re-applied', 'nothing_to_resolve': 'nothing active to resolve',
             'clarify': 'not sure — nothing changed'}
    entry['lines'] = [f"{o['desc']} — {label[o['outcome']]}" + (f" · {o['note']}" if o['note'] and o['outcome'] != 'duplicate' else '')
                      for o in outcomes]
    if changed:
        alerts = impact.build_alerts(fetch_orders(), fetch_incidents(), store.fetch_flags())
        affected = sum(a['severity'] != 'on_track' for a in alerts)
        entry['report_id'] = store.record_report(text, outcomes, affected, undo)
        entry['status'] = 'published' if any(o['outcome'] != 'provisional' for o in changed) else 'provisional'
    elif entry['clarify']:
        entry['status'] = 'clarify'
    else:
        entry['status'] = 'repeat'
    return entry
