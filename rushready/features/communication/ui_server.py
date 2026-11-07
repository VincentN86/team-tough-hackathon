"""SERVER / FRONT-OF-HOUSE UI for Feature 3: the "Kitchen alerts" pane.  Owner: Feature 3 (Liz)

Public entry: render_server_alerts(on_view=None) — the Front Desk layout (frontdesk.py, main UI) places this in its right-hand pane.
  on_view(order_id)  optional callback the layout passes so "View Order" can open that order's packing view. If omitted, no View button.
The pane refreshes itself every few seconds (a Streamlit fragment): an alert the chef publishes shows up WITHOUT any click.
Everything is built from the shared SQLite data (impact.build_alerts) — nothing here is static example text.

Each alert answers four questions in a compact card: what happened (headline), which order (#id), the new ETA (Due -> Est),
and what to do (first suggested action). Buttons only RECORD what staff did; nothing is contacted or cancelled automatically.
Edit here to change: card layout/wording (_alert_card), summary strip (_summary), refresh interval (REFRESH).
"""
import html
from datetime import datetime, timezone

import streamlit as st

from database import fetch_incidents, fetch_orders
from . import impact, store
from .styles import SEVERITY, STATUS_LABEL, inject_styles

REFRESH = '3s'
HANDLED = ('acknowledged', 'customer_contacted', 'awaiting_response')


def _clock(t):
    if not t:
        return '—'
    if isinstance(t, str):
        t = datetime.fromisoformat(t)
    t = t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t
    return t.astimezone().strftime('%I:%M %p').lstrip('0')


def _pill(text, kind=''):
    return f'<span class="rr-pill {kind}">{html.escape(str(text))}</span>'


def _refresh():
    st.rerun()  # full rerun: acknowledging also changes the order rows in the neighbouring pane


# ====================================================================
# UI SECTION: ALERT PANE  (summary strip + active alert cards + collapsed history)
# ====================================================================
def render_server_alerts(on_view=None):
    inject_styles()
    store.init_tables()

    @st.fragment(run_every=REFRESH)
    def live():
        alerts = impact.build_alerts(fetch_orders(), fetch_incidents(), store.fetch_flags(), store.fetch_alert_rows())
        active = [a for a in alerts if a['severity'] != 'on_track' and a['status'] != 'resolved']
        resolved = [a for a in alerts if a['severity'] != 'on_track' and a['status'] == 'resolved']
        badge = _pill(len(active), 'late' if any(a['severity'] in ('urgent', 'delayed') and a['status'] == 'new' for a in active) else '')
        # heading + summary in ONE markdown element (a separate flex-only element gets a collapsed height in Streamlit)
        st.markdown(f"#### Kitchen alerts {badge}\n\n{_summary(alerts)}", unsafe_allow_html=True)
        if not active:
            st.caption('No kitchen alerts. New reports from the chef appear here automatically.')
        for a in active:
            _alert_card(a, on_view)
        if resolved:
            with st.expander(f'Resolved ({len(resolved)})'):
                for a in resolved:
                    st.caption(f"#{a['order']['id']} — {a['headline']}")
        _activity()

    live()


# ====================================================================
# UI SECTION: SUMMARY STRIP — "which orders can still be completed on time?"
# ====================================================================
def _summary(alerts):
    t = impact.timing_summary(alerts)
    parts = [f"On time {t['on_track']}/{len(alerts)}"]
    for key, label, kind in (('at_risk', 'At risk', 'risk'), ('late', 'Late', 'late'), ('blocked', 'Blocked', 'blocked'), ('unknown', 'No estimate', 'info')):
        if t[key]:
            parts.append(_pill(f'{label} {t[key]}', kind))
    return f"<p class='rra-sum'>{' '.join(parts)}</p>"


def _eta_line(a):
    """Due -> Est (+/- vs due). Never invents a time: blocked / unconfirmed alerts say so."""
    t, due = a['timing'], _clock(a['promised_at'])
    if a['revised_at']:
        est = _clock(a['revised_at'])
        tail = f" · {t['late_minutes']} min late" if t['category'] == 'late' else (f" · {t['slack']} min slack" if t['slack'] is not None else '')
        return f'Due {due} · Est {est}{tail}'
    if a['severity'] == 'possible':
        return f'Due {due} · estimate unchanged until confirmed'
    return f'Due {due} · no estimate yet'


# ====================================================================
# UI SECTION: ALERT CARD  (one per affected order)
# ====================================================================
def _alert_card(a, on_view):
    o, oid = a['order'], str(a['order']['id'])
    label, pill_kind = SEVERITY[a['severity']]
    if a['timing']['category'] == 'blocked':
        label = 'Blocked'
    elif a['severity'] == 'delayed' and a['timing']['category'] == 'at_risk':
        label = 'At risk'
    handled = 'handled' if a['status'] in HANDLED else ''
    state = '' if a['status'] == 'new' else f"<span class='rra-state'>{STATUS_LABEL[a['status']]}</span>"
    action = a['actions'][0] if a['actions'] else ''
    with st.container(key=f'rr_alert_{oid}'):
        st.markdown(
            f"<div class='rra sev-{a['severity']} {handled}'>"
            f"<div class='rra-top'><span class='rra-id'>#{html.escape(oid)}</span>{_pill(label, pill_kind)}"
            f"<span class='rra-src'>{html.escape(o['source'])}</span>{state}</div>"
            f"<div class='rra-msg'>{html.escape(a['headline'])}</div>"
            f"<div class='rra-eta'>{html.escape(_eta_line(a))}</div>"
            f"<div class='rra-do'>{html.escape(action)}</div></div>", unsafe_allow_html=True)
        cols = st.columns([1.8, 1.25, 0.85] if on_view else [1.8, 0.9])
        if cols[0].button('Acknowledge', key=f'rrs_{oid}_acknowledged', use_container_width=True,
                          type='primary' if a['status'] == 'new' else 'secondary', disabled=a['status'] != 'new'):
            store.set_alert_status(oid, 'acknowledged', a['signature'])
            _refresh()
        if on_view and cols[1].button('View Order', key=f'rrv_{oid}', use_container_width=True):
            on_view(oid)
        with cols[-1].popover('More', use_container_width=True):
            for status, text in (('customer_contacted', 'Customer contacted'), ('awaiting_response', 'Awaiting response'),
                                 ('resolved', 'Resolve issue')):
                if st.button(text, key=f'rrs_{oid}_{status}', use_container_width=True, disabled=a['status'] == status):
                    store.set_alert_status(oid, status, a['signature'])
                    _refresh()


# ====================================================================
# UI SECTION: COMMUNICATION HISTORY (collapsed unless asked for)
# ====================================================================
def _activity():
    with st.expander('Kitchen activity'):
        reports = store.fetch_reports(10)
        if not reports:
            st.caption('No kitchen reports yet.')
        for r in reports:
            when = datetime.fromisoformat(r['created_at']).astimezone().strftime('%I:%M:%S %p').lstrip('0')
            st.caption(f"{when} — “{r['transcript'][:90]}” → {r['summary']} · {r['affected']} order(s)" + (' · undone' if r['undone'] else ''))
