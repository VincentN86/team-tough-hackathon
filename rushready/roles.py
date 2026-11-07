"""INTEGRATION LAYER — role-based navigation for RushReady.  Owner: shared (Liz + Vincent).

app.py keeps all of Vincent's screens as plain functions (intake, cook queue, packer, front desk ...). This file only
decides WHICH screens each role sees and draws the welcome page + role switcher. It holds no business logic and no data:
both roles read/write the SAME SQLite database through the same functions, so switching roles never resets anything.

Feature 3 is plugged in at exactly two places (search for 'FEATURE 3'):
    Kitchen view -> features.communication.render_voice_panel
    Server view  -> features.communication.render_server_alerts

NOTE: the role is stored in st.session_state, i.e. per browser tab. It is a demo workspace switch, NOT authentication.
"""
import streamlit as st

from features.communication import render_server_alerts, render_voice_panel  # FEATURE 3

ROLE_KEY = 'rr_role'
ROLES = {
    'kitchen': {'icon': '👨‍🍳', 'title': 'CHEF / KITCHEN', 'button': 'Enter Kitchen', 'label': 'Kitchen',
                'points': ['Kitchen orders & prep queue', 'Food prioritization by deadline', 'AI voice communication', 'Preparation status']},
    'server': {'icon': '🛎️', 'title': 'PACKER / SERVER', 'button': 'Enter Front Desk', 'label': 'Front Desk',
               'points': ['Kitchen updates & alerts', 'Orders ready for packing', 'Packing verification', 'Pickup coordination']},
}

# ====================================================================
# UI SECTION: SHARED STYLING for the welcome page and header
# ====================================================================
CSS = '''<style>
.rr-welcome h1{text-align:center;font-size:2.6rem;margin-bottom:0}
.rr-welcome p.sub{text-align:center;font-size:1.25rem;color:#667085;margin-top:4px}
.rr-card-icon{font-size:4rem;text-align:center;line-height:1.1}
.rr-card-title{text-align:center;font-size:1.5rem;font-weight:800;margin:6px 0 10px}
.rr-card ul{margin:0 0 12px 0;padding-left:1.2rem;font-size:1.05rem}
.stButton>button{min-height:3rem}
</style>'''


def current_role():
    return st.session_state.get(ROLE_KEY)


def _pick(role):
    st.session_state[ROLE_KEY] = role


# ====================================================================
# UI SECTION: ROLE SELECTION SCREEN
# Edit here to change the opening page, role cards, labels and layout.
# ====================================================================
def ensure_role_selected():
    """Call once near the top of app.py. Shows the welcome page and stops the script until a role is chosen."""
    if current_role() in ROLES:
        return
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown('<div class="rr-welcome"><h1>🍔 Welcome to RushReady</h1><p class="sub">How are you working today?</p></div>', unsafe_allow_html=True)
    st.write('')
    _, col_a, col_b, _ = st.columns([0.5, 2, 2, 0.5], gap='large')
    for col, role in ((col_a, 'kitchen'), (col_b, 'server')):
        r = ROLES[role]
        with col.container(border=True):
            st.markdown(f'<div class="rr-card"><div class="rr-card-icon">{r["icon"]}</div><div class="rr-card-title">{r["title"]}</div>'
                        f'<ul>{"".join(f"<li>{p}</li>" for p in r["points"])}</ul></div>', unsafe_allow_html=True)
            st.button(r['button'], key=f'enter_{role}', type='primary', use_container_width=True, on_click=_pick, args=(role,))
    st.caption('No login needed for this demo. You can switch between Kitchen and Front Desk at any time; nothing is reset.')
    st.stop()


# ====================================================================
# UI SECTION: ROLE SWITCHER (header)
# ====================================================================
def render_header():
    role = current_role()
    other = 'server' if role == 'kitchen' else 'kitchen'
    st.markdown(CSS, unsafe_allow_html=True)
    left, right = st.columns([5, 2], vertical_alignment='center')
    left.markdown(f"## {ROLES[role]['icon']} Current view: **{ROLES[role]['label']}**")
    right.button(f"Switch to {ROLES[other]['label']}", key='rr_switch', use_container_width=True,
                 on_click=_pick, args=(other,), help='Demo workspace control: changes which screens you see. It does not change permissions or any data.')
    left.caption('Demo workspace switch — not a login. Orders, alerts and packing progress are shared and kept when you switch.')


# ====================================================================
# UI SECTION: KITCHEN DASHBOARD (Chef workspace)
# ====================================================================
def render_kitchen(screens, key, model):
    # FEATURE 3: voice panel sits ABOVE the tabs so it stays in one stable place (the microphone keeps listening
    # while the chef works) and is the first thing on the page.
    render_voice_panel(key, model)
    st.divider()
    t_queue, t_orders, t_legacy = st.tabs(['👨‍🍳 Prep queue & tickets', '📥 Incoming orders', '🗒️ Original typed report'])
    with t_queue:
        screens['cook']()
    with t_orders:
        screens['intake']()
    with t_legacy:
        st.caption("Vincent's original typed chef report. It still works and writes to the same incident list.")
        screens['legacy_agent']()


# ====================================================================
# UI SECTION: SERVER DASHBOARD (Packer / Front-of-house workspace)
# ====================================================================
def render_server(screens):
    render_server_alerts()  # FEATURE 3: counters + kitchen alerts + recommended actions (auto-refreshing)
    st.divider()
    t_pack, t_pickup, t_new, t_notes = st.tabs(['📦 Packing checklist', '🛎️ Pickup & handoff', '📥 Take a new order', 'ℹ️ Notes'])
    with t_pack:
        screens['packer']()
    with t_pickup:
        screens['front_desk']()
    with t_new:
        screens['intake']()
    with t_notes:
        screens['notes']()


def run_app(screens, key, model):
    """screens: dict of zero-argument functions from app.py: cook, legacy_agent, intake, packer, front_desk, notes."""
    render_header()
    if current_role() == 'kitchen':
        render_kitchen(screens, key, model)
    else:
        render_server(screens)
