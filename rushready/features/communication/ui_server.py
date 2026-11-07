"""SERVER / FRONT-OF-HOUSE UI for Feature 3: status dashboard, kitchen alert cards, activity log.  Owner: Feature 3 (Liz)

Public entry: render_server_alerts()  — roles.py calls it at the top of Front Desk view.
The panel refreshes itself every few seconds (a Streamlit fragment), so a second browser session showing the Server
view sees alerts the chef publishes WITHOUT any click. Everything is built from the shared SQLite data.

Edit here to change: alert card layout/wording, dashboard counters, refresh interval (REFRESH).
"""
import html
from datetime import datetime, timezone

import streamlit as st

from database import fetch_incidents, fetch_orders
from . import impact, store
from .styles import SEVERITY, STATUS_LABEL, inject_styles

REFRESH = '3s'


def _clock(t):
    if not t:
        return '—'
    if isinstance(t, str):
        t = datetime.fromisoformat(t)
        t = t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t
    return t.astimezone().strftime('%I:%M %p').lstrip('0')


def _items(o):
    return ' + '.join(f"{i['quantity']}× {i['name']}" for i in o['items'])


def _refresh():
    try:
        st.rerun(scope='fragment')
    except TypeError:  # very old Streamlit
        st.rerun()


# ====================================================================
# UI SECTION: SERVER DASHBOARD  (counters + alerts + activity)
# ====================================================================
def render_server_alerts():
    inject_styles()
    store.init_tables()

    @st.fragment(run_every=REFRESH)
    def live():
        orders = fetch_orders()
        alerts = impact.build_alerts(orders, fetch_incidents(), store.fetch_flags(), store.fetch_alert_rows())
        _counters(orders, alerts)
        _timing_line(alerts)
        active = [a for a in alerts if a['severity'] != 'on_track' and a['status'] != 'resolved']
        ok = [a for a in alerts if a['severity'] == 'on_track']
        resolved = [a for a in alerts if a['severity'] != 'on_track' and a['status'] == 'resolved']

        st.subheader(f'🚨 Kitchen alerts ({len(active)})')
        if not active:
            st.caption('No active kitchen alerts. When the chef reports a problem it appears here automatically.')
        for a in active:
            _alert_card(a)
        with st.expander(f'✅ Unaffected — continue normally ({len(ok)})', expanded=not active):
            for a in ok:
                o = a['order']
                st.markdown(f"**ON TRACK — ORDER #{o['id']}** · {_items(o)} · {o['source']} · pickup {_clock(a['promised_at'])} · {_timing_text(a)}  \n"
                            'No known kitchen issues. Suggested action: continue preparing and packing normally.')
        if resolved:
            with st.expander(f'Resolved ({len(resolved)})'):
                for a in resolved:
                    st.caption(f"Order #{a['order']['id']} — resolved")
        _activity()

    live()


# ====================================================================
# UI SECTION: SERVER DASHBOARD COUNTERS
# ====================================================================
TIMING_LABEL = {'on_track': '🟢 On track', 'at_risk': '🟡 At risk', 'late': '🔴 Likely late', 'blocked': '⛔ Blocked', 'unknown': '❔ No estimate'}


def _timing_line(alerts):
    # "Which orders can still be completed on time?" — counts ALL open orders, not just the affected ones
    t = impact.timing_summary(alerts)
    st.markdown(f"**Can still be completed on time:** {t['on_track']} of {len(alerts)}  ·  "
                f"🟡 {t['at_risk']} at risk  ·  🔴 {t['late']} likely late  ·  ⛔ {t['blocked']} blocked  ·  ❔ {t['unknown']} no estimate")


def _timing_text(a):
    t = a['timing']
    if t['category'] == 'late':
        return f"{TIMING_LABEL['late']} by about {t['late_minutes']} min"
    if t['category'] in ('on_track', 'at_risk') and t['slack'] is not None:
        return f"{TIMING_LABEL[t['category']]} · {t['slack']} min slack"
    return TIMING_LABEL[t['category']]


def _counters(orders, alerts):
    prep = sum(o['status'] in ('queued', 'cooking') for o in orders)
    to_pack = sum(o['status'] == 'ready_to_pack' for o in orders)
    pickup = sum(o['status'] == 'packed' for o in orders)
    attention = sum(a['severity'] == 'urgent' and a['status'] in ('new', 'acknowledged') for a in alerts)
    new = sum(a['severity'] != 'on_track' and a['status'] == 'new' for a in alerts)
    cols = st.columns(5)
    for col, (label, val) in zip(cols, [('Preparing', prep), ('Ready to pack', to_pack), ('Ready for pickup', pickup),
                                        ('Need customer attention', attention), ('New alerts', new)]):
        col.metric(label, val)


# ====================================================================
# UI SECTION: SERVER ALERT CARDS
# ====================================================================
def _alert_card(a):
    o = a['order']
    label, bg, fg = SEVERITY[a['severity']]
    with st.container(border=True):
        st.markdown(f"<div class='rr-banner' style='background:{bg};color:{fg}'>{label} — ORDER #{html.escape(str(o['id']))}"
                    f"<small>{html.escape(o['source'])}</small></div>", unsafe_allow_html=True)
        st.markdown(f"#### {a['headline']}")
        st.write(f"**{_items(o)}**  ·  Timing: {_timing_text(a)}")
        st.markdown('**What happened / why this order is affected:**')
        for text, certainty in a['reasons']:
            st.markdown(f"- {text}" + ('  `unconfirmed`' if certainty == 'provisional' else ''))
        st.write(f"Original promised ready time: **{_clock(a['promised_at'])}**")
        if a['revised_at']:
            st.write(f"Revised estimated ready time: **≈ {_clock(a['revised_at'])}** (estimate from the kitchen schedule)")
        elif a['severity'] in ('urgent',):
            st.write('Revised estimated ready time: **unknown** until the kitchen reports one')
        st.write('**Suggested action:** ' + ' '.join(a['actions']))
        st.write('**Status:** ' + STATUS_LABEL[a['status']])
        cols = st.columns(4)
        for col, (status, text) in zip(cols, [('acknowledged', 'Acknowledge Alert'), ('customer_contacted', 'Customer Contacted'),
                                              ('awaiting_response', 'Awaiting Response'), ('resolved', 'Issue Resolved')]):
            if col.button(text, key=f"rrs_{o['id']}_{status}", use_container_width=True,
                          type='primary' if a['status'] == status else 'secondary'):
                store.set_alert_status(o['id'], status, a['signature'])
                _refresh()
        st.caption('Buttons only record what staff actually did. Nothing is cancelled, contacted or approved automatically.')


# ====================================================================
# UI SECTION: COMMUNICATION ACTIVITY
# ====================================================================
def _activity():
    st.subheader('🗒️ Communication activity')
    reports = store.fetch_reports(10)
    if not reports:
        st.caption('No kitchen reports yet.')
    for r in reports:
        when = datetime.fromisoformat(r['created_at']).astimezone().strftime('%I:%M:%S %p').lstrip('0')
        st.write(f"{when} — Chef said “{r['transcript'][:90]}” → {r['summary']} · {r['affected']} order(s) affected"
                 + (' · *undone*' if r['undone'] else ''))
