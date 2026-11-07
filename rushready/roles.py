"""MAIN-APP SHELL — role state, compact top bar, secondary navigation and workspace composition.  Owner: main BREDDY UI.

app.py keeps the team's screens as plain functions (intake, cook queue, packer, front desk ...). This file decides WHICH screens each
role sees and how they are arranged. It holds no business logic and no data: both roles read/write the SAME SQLite database, so
switching roles never resets anything.   NOTE: the role lives in st.session_state (per browser tab) — a demo switch, NOT authentication.

Composition (search for 'FEATURE' to find where feature code is plugged in):
    Kitchen    ONE screen. left pane: Feature 2 queue (screens['cook']) + collapsed 'Incoming orders'
               right pane: Feature 3 voice panel (render_voice_panel) + collapsed original typed report.
               A draggable divider (ui/splitpane.py) sits between the panes (default 60/40).
    Front Desk left pane: order rows + packing view (frontdesk.py)  right pane: Feature 3 alert cards (render_server_alerts)

WHERE TO EDIT
    Top bar (brand, role chip, nav, status chips, switch) ... render_topbar()
    Front Desk navigation items ............................. SERVER_NAV
    Kitchen layout / default split / limits ................. render_kitchen()  (limits: ui/splitpane.py)
    Colours / fonts / spacing / pane scrolling .............. ui/theme.py
    Landing screen .......................................... landing.py
"""
import streamlit as st

from database import fetch_incidents, fetch_orders
from features.communication import render_voice_panel  # FEATURE 3
from frontdesk import render_orders_workspace           # Front Desk layout (main UI)
from landing import BRAND, render_role_picker
from scheduler import schedule                           # core: only to show late/blocked counts in the top bar
from ui.splitpane import render_splitter
from ui.theme import inject_theme

ROLE_KEY = 'rr_role'
ROLES = {
    'kitchen': {'title': 'CHEF / KITCHEN', 'button': 'Enter Kitchen', 'label': 'Kitchen'},
    'server': {'title': 'PACKER / SERVER', 'button': 'Enter Front Desk', 'label': 'Front Desk'},
}
SERVER_NAV = {'orders': 'Orders', 'new': 'New order', 'classic': 'Classic', 'notes': 'Notes'}   # Kitchen has no secondary navigation


def current_role():
    return st.session_state.get(ROLE_KEY)


def _pick(role):
    st.session_state[ROLE_KEY] = role


def ensure_role_selected():
    """Call once near the top of app.py. Shows the landing screen and stops the script until a role is chosen."""
    if current_role() in ROLES:
        return
    render_role_picker(ROLES, _pick)
    st.stop()


# ====================================================================
# UI SECTION: TOP BAR — brand, role chip, (Front Desk: secondary nav), live status, role switch (one compact row)
# ====================================================================
def _status_chips():
    ranked = schedule(fetch_orders(), fetch_incidents())
    late = sum(r['urgency'] == 'LATE' for r in ranked)
    blocked = sum(r['blocked'] for r in ranked)
    chips = [f'{len(ranked)} open']
    if late:
        chips.append(f'<span class="rr-pill late">{late} late</span>')
    if blocked:
        chips.append(f'<span class="rr-pill blocked">{blocked} blocked</span>')
    return f"<div class='rr-chips'>{' '.join(chips)}</div>"


def render_topbar(role):
    """Returns the selected secondary-view key (Front Desk only; the Kitchen is a single screen)."""
    other = 'server' if role == 'kitchen' else 'kitchen'
    with st.container(key='rr_topbar'):
        cols = st.columns([2.4, 4.0, 1.8, 1.9] if role == 'server' else [3.0, 5.0, 2.0], vertical_alignment='center')
        cols[0].markdown(f"<span class='rr-brand'>{BRAND}</span><span class='rr-rolechip'>{ROLES[role]['label']}</span>", unsafe_allow_html=True)
        choice = None
        if role == 'server':
            choice = cols[1].segmented_control('View', options=list(SERVER_NAV), format_func=SERVER_NAV.get, default='orders',
                                               key='rr_nav_server', label_visibility='collapsed')
        cols[-2].markdown(_status_chips(), unsafe_allow_html=True)
        cols[-1].button(f"Switch to {ROLES[other]['label']}", key='rr_switch', use_container_width=True, on_click=_pick, args=(other,),
                        help='Changes which screens you see. It does not change permissions or any data.')
    return choice or 'orders'


# ====================================================================
# UI SECTION: KITCHEN WORKSPACE — one screen, two panes, draggable divider.
# The voice pane is ALWAYS rendered so the microphone keeps listening.
# ====================================================================
def render_kitchen(screens, key, model):
    left, right = st.columns([3, 2], gap='small')                                   # 60 / 40 default; the divider changes it live
    with left, st.container(key='rr_pane_queue'):
        with st.expander('Incoming orders'):                                          # was a separate page: kept, but collapsed
            screens['intake']()
        screens['cook']()                                                             # FEATURE 2: ticket queue
    with right, st.container(key='rr_pane_voice'):
        render_voice_panel(key, model)                                                # FEATURE 3: mic, typed report, recent alerts
        with st.expander('Manual report (original)'):                                 # was a separate page: kept, but collapsed
            screens['legacy_agent']()
    render_splitter('rr_pane_queue', 'rr_pane_voice')                                 # draggable divider (main UI)


# ====================================================================
# UI SECTION: FRONT DESK WORKSPACE
# ====================================================================
def render_server(screens, view):
    if view == 'orders':
        render_orders_workspace()
    else:
        with st.container(key='rr_pane_secondary'):
            {'new': screens['intake'], 'classic': lambda: (screens['packer'](), st.divider(), screens['front_desk']()),
             'notes': screens['notes']}[view]()


def run_app(screens, key, model):
    """screens: dict of zero-argument functions from app.py: cook, legacy_agent, intake, packer, front_desk, notes."""
    inject_theme()
    role = current_role()
    view = render_topbar(role)
    if role == 'kitchen':
        render_kitchen(screens, key, model)
    else:
        render_server(screens, view)
