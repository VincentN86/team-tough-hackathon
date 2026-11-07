"""KITCHEN-SIDE UI for Feature 3: microphone, live feed of what the system did, pending advisories.  Owner: Feature 3 (Liz)

Public entry: render_voice_panel(key, model)  — roles.py calls it at the top of Kitchen View.
There is NO "confirm / publish" step: each finished sentence is interpreted and, depending on confidence, published
automatically (see store._apply). The chef can Undo, or confirm/dismiss tentative advisories, afterwards.

Edit here to change: panel layout, feed wording, advisory buttons. Microphone look/behaviour: voice_component/index.html
"""
import html
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from . import pipeline, store
from .styles import inject_styles

_voice = components.declare_component('chef_voice_live', path=str(Path(__file__).parent / 'voice_component'))

# ====================================================================
# UI SECTION: VOICE PANEL  (microphone + typed fallback + live feed)
# ====================================================================
def render_voice_panel(key='', model='openrouter/auto'):
    inject_styles()
    store.init_tables()
    ss = st.session_state
    ss.setdefault('vc_feed', [])      # what we did with each statement (this browser session only)
    ss.setdefault('vc_seen', set())   # utterance ids already processed
    ss.setdefault('vc_recent', {})    # repeat protection

    st.markdown('#### Voice Communication')

    # ----- UI SECTION: MICROPHONE CONTROLS (component keeps its place on reruns; keep this call position stable)
    value = _voice(key='chef_voice_live', default=None)
    for u in (value or {}).get('utterances', []):
        if u['id'] not in ss['vc_seen']:
            ss['vc_seen'].add(u['id'])
            _handle(u['text'], key, model)

    # ----- UI SECTION: TYPED FALLBACK (same pipeline as speech)
    with st.form('vc_typed', clear_on_submit=True, border=False):
        c1, c2 = st.columns([3, 1], vertical_alignment='bottom')
        typed = c1.text_input('Type a report', key='vc_typed_text', label_visibility='collapsed',
                              placeholder="Type a report, e.g. the fryer is ten minutes behind")
        sent = c2.form_submit_button('Send', use_container_width=True, type='primary')
    if sent and typed.strip():
        _handle(typed, key, model)

    _render_feed()
    _render_advisories()
    _render_active()


def _handle(text, key, model):
    entry = pipeline.process_utterance(text, key, model, recent=st.session_state['vc_recent'])
    if entry['status'] != 'repeat':
        st.session_state['vc_feed'].insert(0, entry)
        del st.session_state['vc_feed'][12:]


# ====================================================================
# UI SECTION: VOICE TRANSCRIPT / WHAT THE SYSTEM DID
# ====================================================================
STATUS_TEXT = {'published': 'Sent to Front Desk', 'provisional': 'Sent as possible issue', 'clarify': 'Not sure — nothing changed',
               'ignored': 'Ignored (not about orders)', 'repeat': 'Repeat'}


def _render_feed():
    feed = st.session_state['vc_feed']
    if not feed:
        return
    undone = {r['id'] for r in store.fetch_reports() if r['undone']}
    for n, e in enumerate(feed[:5]):   # recent only: the pane stays compact (full history is kept in the Front Desk 'Kitchen activity')
        lines = '<br>'.join(html.escape(x) for x in e['lines'])
        st.markdown(f"<div class='rr-feed {e['status']}'><b>{STATUS_TEXT[e['status']]}</b> · “{html.escape(e['text'])}”"
                    f"<br><small>{lines}</small></div>", unsafe_allow_html=True)
        for o in e['clarify']:
            st.caption('Question: ' + (o['question'] or o['note'] or 'Please repeat with the station / order and minutes.'))
        rid = e['report_id']
        if rid and rid not in undone:
            if st.button('Undo this report', key=f'vc_undo_{rid}_{n}'):
                store.undo_report(rid)
                st.rerun()
        elif rid:
            st.caption('(undone)')


# ====================================================================
# UI SECTION: KITCHEN ISSUE ALERTS — tentative advisories waiting for the chef (optional, one tap)
# ====================================================================
def _render_advisories():
    flags = [f for f in store.fetch_flags() if f['active'] and f['certainty'] == 'provisional']
    if not flags:
        return
    st.markdown('**Possible issues** — sent to Front Desk as tentative')
    for f in flags:
        k = f['kind']
        with st.container(border=True):
            c1 = st.container()
            c2, c3 = st.columns([2, 1], vertical_alignment='center')
            c1.write({'ingredient_unavailable': f"Possible: **{f['ingredient']}** unavailable",
                      'ingredient_low': f"Low stock: **{f['ingredient']}**",
                      'prep_wait': f"Cooked **{f['ingredient']}** not ready yet (not a shortage)",
                      'order_issue': f"**{f['ingredient'] or 'Item'}** may be missing on order #{f['order_id']}",
                      'delay_unknown': f"**{f['station']}** behind — how long?",
                      'item_delay': f"**{f['item']}** may be late — how long?"}.get(k, k))
            if k in ('ingredient_unavailable', 'ingredient_low'):
                if c2.button('Yes, it is out', key=f"vc_ok_{f['id']}", use_container_width=True):
                    store.confirm_flag(f['id'])
                    st.rerun()
            elif k in ('delay_unknown', 'item_delay'):
                mins = c2.number_input('Minutes', 1, 120, 10, key=f"vc_m_{f['id']}", label_visibility='collapsed')
                if c2.button('Set delay', key=f"vc_ok_{f['id']}", use_container_width=True):
                    store.confirm_flag(f['id'], int(mins))
                    st.rerun()
            if c3.button('Dismiss', key=f"vc_no_{f['id']}", use_container_width=True):
                store.dismiss_flag(f['id'])
                st.rerun()


# ====================================================================
# UI SECTION: ACTIVE REPORTS (correct a mistake: resolve anything that is no longer true)
# ====================================================================
def _render_active():
    from database import fetch_incidents, resolve_incident
    incs = [x for x in fetch_incidents() if x['active']]
    flags = [f for f in store.fetch_flags() if f['active'] and f['certainty'] == 'confirmed']
    if not incs and not flags:
        return
    with st.expander(f'Active reports ({len(incs) + len(flags)})'):
        for x in incs:
            c1, c2 = st.columns([5, 1])
            c1.write(x['ingredient'] + ' unavailable' if x['ingredient'] else f"{x['station']} {x['delay_minutes']} min behind")
            if c2.button('Resolve', key=f"vc_ri_{x['id']}", use_container_width=True):
                resolve_incident(x['id'])
                st.rerun()
        for f in flags:
            c1, c2 = st.columns([5, 1])
            c1.write(store.describe({'type': f['kind'], 'ingredient': f['ingredient'], 'station': f['station'], 'order_id': f['order_id'],
                                     'delay_minutes': f['delay_minutes'], 'item': f['item'], 'mode': f['mode']}))
            if c2.button('Resolve', key=f"vc_rf_{f['id']}", use_container_width=True):
                store.resolve_flag(f['id'])
                st.rerun()
