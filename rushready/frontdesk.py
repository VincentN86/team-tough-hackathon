"""MAIN-APP UI — Front Desk workspace layout.  Owner: main BREADY UI (shell). Contains NO feature logic.

Two panes that stay visible together and scroll INSIDE themselves (the page does not scroll):
    LEFT  (rr_pane_orders)  compact order rows grouped by what to do next; picking one opens the focused packing view in this same pane
    (a draggable divider between the panes, same component as the Kitchen)
    RIGHT (rr_pane_alerts)  Feature 3's kitchen-alert cards (features.communication.render_server_alerts) — always visible, even while packing
Data comes only from shared services: database.fetch_orders (core) and features.communication.order_alerts (Feature 3, read-only).
Packing actions live in packing.py (Feature 4 logic, unchanged).

WHERE TO EDIT
    Pane width ratio ............ PANE_RATIO
    What a row shows ............ _row()
    Row grouping / order ........ SECTIONS, _section()
    Row action button labels .... SECTIONS (label)
    Row look .................... CSS below
"""
import html

import streamlit as st

from database import fetch_orders, handoff_order
from features.communication import order_alerts, render_server_alerts  # FEATURE 3 public API
from packing import render_packing_detail
from ui.splitpane import render_splitter
from ui.theme import clock, inject_css, pill

PANE_RATIO = [3, 2]   # orders : alerts = 60 / 40 default; the draggable divider (ui/splitpane.py) changes it live
SELECTED = 'fd_selected'
# section key -> (heading, primary action label). Order here = order on screen.
SECTIONS = {
    'pack': ('Pack now', 'Pack Order'),
    'packing': ('Packing in progress', 'Continue Packing'),
    'handoff': ('Ready for handoff', 'Hand Off'),
    'waiting': ('Awaiting food', 'View Order'),
}

CSS = '''<style>
.fd-sec{font-size:.78rem;font-weight:800;letter-spacing:.06em;text-transform:uppercase;color:var(--rr-muted,#555);margin:8px 0 1rem}   /* 1rem bottom offsets Streamlit's -1rem markdown margin */
.fd-row{border:1px solid var(--rr-line,#c9c9c9);border-left:4px solid var(--rr-line-strong,#767676);background:var(--rr-surface,#f5f5f5);border-radius:0 6px 6px 0;padding:4px 10px;margin-bottom:1rem}   /* 1rem: offsets Streamlit's -1rem markdown margin */
.fd-row.late{border-left-color:var(--rr-late,#b42318)}
.fd-row.at_risk{border-left-color:var(--rr-risk,#93370d)}
.fd-row.blocked{border-left-color:var(--rr-blocked-bg,#1f2937)}
.fd-top{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.fd-id{font-weight:800;font-size:1.05rem}
.fd-meta{font-size:.85rem;color:var(--rr-muted,#66645f);font-variant-numeric:tabular-nums}
.fd-items{font-size:.9rem;margin-top:2px}
</style>'''


def _section(o):
    if o['status'] == 'packed':
        return 'handoff'
    if o['status'] == 'ready_to_pack':
        return 'packing' if any(i['pack_verified'] for i in o['items']) else 'pack'
    return 'waiting'


def open_order(order_id):
    st.session_state[SELECTED] = str(order_id)
    st.rerun()


def _close():
    st.session_state.pop(SELECTED, None)
    st.rerun()


def _timing_pill(a):
    t = a['timing'] if a else None
    if not t or t['category'] == 'on_track':
        return ''
    if t['category'] == 'late':
        return pill(f"Late {t['late_minutes']} min", 'late')
    return pill({'blocked': 'Blocked', 'at_risk': 'At risk', 'unknown': 'No estimate'}[t['category']],
                {'blocked': 'blocked', 'at_risk': 'risk', 'unknown': 'info'}[t['category']])


# ====================================================================
# UI SECTION: ORDER ROW  (id, source, due/estimate, status, alert, safety flags, items, ONE primary action)
# ====================================================================
def _row(o, sec, a):
    cat = a['timing']['category'] if a else 'on_track'
    est = ''
    if a and a['revised_at'] and a['severity'] != 'on_track':
        est = f" · est {clock(a['revised_at'])}"
    elif a and a['timing']['category'] == 'blocked':
        est = ' · no estimate'
    tags = _timing_pill(a)
    if a and a['severity'] == 'possible':
        tags += ' ' + pill('Tentative alert', 'tentative')
    if any(i['allergy'] for i in o['items']):
        tags += ' ' + pill('Allergy', 'late')           # safety flag stays visible on the row
    if any(i['modifier'] for i in o['items']):
        tags += ' ' + pill('Mods')
    items = ' · '.join(f"{i['quantity']}× {i['name']}" for i in o['items'])
    with st.container(key=f"rr_row_{o['id']}"):
        left, right = st.columns([4.4, 1.5], vertical_alignment='center')
        left.markdown(f"<div class='fd-row {cat}'><div class='fd-top'><span class='fd-id'>#{html.escape(str(o['id']))}</span>"
                      f"<span class='fd-meta'>{html.escape(o['source'])} · due {clock(o['pickup_at'])}{est}</span></div>"
                      f"<div class='fd-items'>{tags} {html.escape(items)}</div></div>", unsafe_allow_html=True)
        label = SECTIONS[sec][1]
        if right.button(label, key=f"rr_open_{o['id']}", use_container_width=True, type='primary' if sec in ('pack', 'handoff') else 'secondary'):
            if sec == 'handoff':
                if handoff_order(o['id']):
                    st.toast(f"#{o['id']} handed off")
                    st.rerun()
            else:
                open_order(o['id'])


# ====================================================================
# UI SECTION: LEFT PANE — order list, or the packing view for the selected order
# ====================================================================
def _orders_pane():
    selected = st.session_state.get(SELECTED)
    open_orders = [o for o in fetch_orders() if o['status'] != 'handed_off']
    chosen = next((o for o in open_orders if o['id'] == selected), None)
    if chosen:
        render_packing_detail(chosen, order_alerts().get(chosen['id']), _close)   # no auto-refresh here: don't disturb a checklist in progress
        return
    st.session_state.pop(SELECTED, None)

    @st.fragment(run_every='5s')
    def listing():
        orders = [o for o in fetch_orders() if o['status'] != 'handed_off']
        alerts = order_alerts()
        inject_css(CSS)
        if not orders:
            st.caption('No open orders.')
        groups = {k: sorted([o for o in orders if _section(o) == k], key=lambda o: o['pickup_at']) for k in SECTIONS}
        for key, (heading, _) in SECTIONS.items():
            if groups[key]:
                st.markdown(f"<div class='fd-sec'>{heading} · {len(groups[key])}</div>", unsafe_allow_html=True)
                for o in groups[key]:
                    _row(o, key, alerts.get(o['id']))

    listing()


# ====================================================================
# UI SECTION: WORKSPACE (two panes side by side)
# ====================================================================
def render_orders_workspace():
    left, right = st.columns(PANE_RATIO, gap='small')
    with left, st.container(key='rr_pane_orders'):
        _orders_pane()
    with right, st.container(key='rr_pane_alerts'):
        render_server_alerts(on_view=open_order)
    render_splitter('rr_pane_orders', 'rr_pane_alerts', default=0.6)   # draggable divider between the order list and the kitchen alerts
