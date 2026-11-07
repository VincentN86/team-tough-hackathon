"""TICKET MODULE — kitchen tickets as a vertical tab rail + the selected ticket's details.  Owner: ticket / prioritization feature (Feature 2).

DESIGN CREDIT: the paper-ticket look (cream paper, Courier New typewriter font, coloured platform strip, torn zig-zag bottom edge, dashed "cut"
lines, magenta allergy box, status chips) and the per-item Start / Ready controls come from Jiena Lee's `tickets` commit
(origin/main 796e717, rushready/app.py: ticket_html(), opened_ticket(), the .ticket / .bt-* CSS). Her branch was NOT merged or modified:
that markup was ported into this module and adapted to (a) live INSIDE the left pane of the Kitchen split screen, and (b) be a vertical tab rail.

DATA: nothing is hardcoded. Order order + urgency come from the existing scheduler (`scheduler.schedule`, unchanged); items and statuses
come from the shared database; an optional `alerts_fn` (passed in by roles.py) supplies Feature 3's revised ETAs and kitchen messages, so this
module never imports the communication package.

LAYOUT:   [ tab rail (dark, ~30% of the pane, 150-250px) | selected ticket ]   The rail is sticky and scrolls on its own if there are many orders.
SELECTION: kept by ORDER ID in st.session_state['open_ticket'] — if priorities reorder, the same order stays open. Default = top-priority order.

WHERE TO EDIT
    Ticket look (paper, fonts, chips, allergy box) ... CSS  (the --tk-* variables at the top)
    What a tab shows ................................ tab_html()
    What the opened ticket shows .................... render_detail()
    Ticket font ..................................... --tk-font (Courier New is Jiena's choice; any single serif can replace it here)
"""
import html

import streamlit as st

from database import fetch_incidents, fetch_orders, update_item
from scheduler import batch_hints, remaining_minutes, schedule   # existing scheduling logic, unchanged
from ui.theme import clock, inject_css

SELECTED = 'open_ticket'            # same session key Jiena used
TICKET_COLORS = {'DoorDash': '#e8320b', 'Uber Eats': '#05a357', 'Website': '#7c4ddb', 'Phone': '#2563eb', 'In-person POS': '#444'}  # hers

# ====================================================================
# CSS — scoped to .tk-* / .st-key-tk_*  (one single <style> block via inject_css; no blank lines!)
# ====================================================================
CSS = '''<style>
:root{--tk-font:"Courier New",Courier,monospace;--tk-paper:#fffdf4;--tk-paper-dim:#e6e1cf;--tk-ink:#1d1d1d;--tk-muted:#555;--tk-cut:#b9b2a0;
  --tk-allergy:#c0157a;--tk-allergy-bg:#ffe3f2;--tk-allergy-ink:#8a0050;--tk-rail:#191919;}
/* ticket text keeps the ticket font even though the app font is Lexend (higher specificity than the global font rule) */
[data-testid="stApp"] .tk-paper.tk-paper,[data-testid="stApp"] .tk-paper.tk-paper *{font-family:var(--tk-font) !important;}   /* doubled class = beats the global Lexend rule */
/* ---- layout: dark rail + selected ticket, side by side inside the left pane ---- */
.st-key-tk_layout [data-testid="stHorizontalBlock"]{flex-wrap:nowrap !important;gap:12px;align-items:flex-start;}
.st-key-tk_layout [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child{flex:0 0 clamp(150px,30%,250px) !important;width:auto !important;min-width:150px !important;}
.st-key-tk_layout [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:last-child{flex:1 1 0 !important;min-width:0 !important;width:auto !important;}
.st-key-tk_rail{position:sticky;top:0;max-height:calc(100vh - 190px);overflow-y:auto;background:var(--tk-rail);border-radius:8px;padding:8px 0 8px 8px;gap:0 !important;}
/* ---- a tab: compact ticket. Tabs touch each other (one roll), separated by a dashed cut ---- */
.st-key-tk_rail .stVerticalBlock[class*="st-key-tk_tab_"]{position:relative;gap:0;}
[class*="st-key-tk_open_"]{position:absolute !important;inset:0;width:100% !important;height:100% !important;z-index:3;margin:0;}
[class*="st-key-tk_open_"] .stButton,[class*="st-key-tk_open_"] .stButton>div,[class*="st-key-tk_open_"] button{width:100%;height:100%;}
[class*="st-key-tk_open_"] button{opacity:0;cursor:pointer;}
[class*="st-key-tk_tab_"] [data-testid="stMarkdownContainer"]{margin-bottom:0;}
[class*="st-key-tk_tab_"]:has(button:focus-visible) .tk-tab{outline:3px solid #fff;outline-offset:-3px;}
.tk-tab{background:var(--tk-paper-dim);color:#444;padding:8px 10px 8px 9px;border-left:6px solid var(--src,#555);border-bottom:2px dashed var(--tk-cut);margin-bottom:0;}
.tk-tab:hover{background:#efead9;}
.tk-tab.sel{background:var(--tk-paper);color:var(--tk-ink);border-left:6px solid #ff3008;box-shadow:inset 0 0 0 2px var(--tk-ink);}
.tk-tab .tk-top{display:flex;justify-content:space-between;align-items:baseline;gap:6px;}
.tk-tab .tk-no{font-size:19px;font-weight:700;letter-spacing:.5px;}
.tk-tab .tk-rank{font-size:11px;font-weight:700;color:#777;margin-right:4px;}
.tk-tab.sel .tk-rank{color:#ff3008;}
.tk-src{font-size:10px;font-weight:700;text-transform:uppercase;color:#fff;background:var(--src,#555);padding:1px 5px;border-radius:3px;white-space:nowrap;}
.tk-tab .tk-row{display:flex;justify-content:space-between;align-items:center;gap:6px;margin-top:3px;font-size:12px;}
.tk-tab .tk-sub{font-size:11.5px;color:#555;margin-top:2px;}
.tk-status{font-size:10.5px;font-weight:700;text-transform:uppercase;border:1.5px solid var(--tk-ink);padding:0 4px;}
.tk-urg{font-size:10.5px;font-weight:700;text-transform:uppercase;padding:0 5px;white-space:nowrap;}
.tk-urg.late{color:#b42318;border:1.5px solid #b42318;}
.tk-urg.risk{color:#93370d;border:1.5px solid #93370d;background:#fef0c7;}
.tk-urg.blocked{color:#fff;background:#191919;border:1.5px solid #191919;}
.tk-urg.ok{color:#067647;}
.tk-flag{display:inline-block;margin-top:4px;font-size:10.5px;font-weight:700;color:var(--tk-allergy-ink);background:var(--tk-allergy-bg);border:2px solid var(--tk-allergy);padding:0 5px;}
/* narrow left pane (the divider was dragged): drop the secondary lines of each tab, keep number / urgency / allergy */
.st-key-rr_pane_queue{container-type:inline-size;}
@container (max-width:480px){.tk-tab .tk-sub,.tk-tab .tk-src{display:none;}.tk-tab .tk-no{font-size:17px;}}
/* ---- opened ticket (Jiena's big ticket, scaled to fit a pane) ---- */
.st-key-tk_detail{background:var(--tk-paper);color:var(--tk-ink);padding:16px 20px 36px;border-top:10px solid var(--bt-src,#555);border-radius:6px 6px 0 0;
  -webkit-mask:conic-gradient(from -45deg at bottom,#0000,#000 1deg 89deg,#0000 90deg) 50%/16px 100%;
          mask:conic-gradient(from -45deg at bottom,#0000,#000 1deg 89deg,#0000 90deg) 50%/16px 100%;}
.st-key-tk_detail [data-testid="stMarkdownContainer"]{color:var(--tk-ink);}
.st-key-tk_detail button{background:#fff;color:var(--tk-ink);border:2px solid var(--tk-ink);font-weight:700;min-height:2.9rem;}
.st-key-tk_detail button:hover{background:var(--tk-ink);color:var(--tk-paper);}
.st-key-tk_detail button:disabled{background:transparent;color:#8c8778;border-color:#c9c3b2;}
.st-key-tk_detail button p{font-size:.95rem !important;white-space:nowrap;}
.st-key-tk_detail [data-testid="stBaseButton-primary"]{background:#ff3008;border-color:#ff3008;color:#fff;}
.st-key-tk_detail [data-testid="stBaseButton-primary"]:hover{background:#d92806;border-color:#d92806;color:#fff;}
.bt-head{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;}
.bt-no{font-size:40px;font-weight:700;letter-spacing:1px;line-height:1;}
.bt-src{font-size:14px;font-weight:700;text-transform:uppercase;color:#fff;background:var(--bt-src,#555);padding:3px 9px;border-radius:4px;}
.bt-chip{font-size:12px;font-weight:700;text-transform:uppercase;border:2px solid var(--tk-ink);padding:1px 7px;}
.bt-chip.cooking{background:#ffd23f;}
.bt-chip.ready{background:#2fbf71;border-color:#1a7a46;}
.bt-facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:6px 14px;margin-top:10px;font-size:13px;}
.bt-facts div{border-left:3px solid var(--tk-cut);padding-left:7px;}
.bt-facts b{display:block;font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--tk-muted);}
.bt-facts span{font-size:15px;font-weight:700;}
.bt-why{margin-top:10px;font-size:13px;}
.bt-delay{margin-top:8px;border:2px solid #b42318;background:#fee4e2;color:#7a1a12;font-weight:700;font-size:13px;padding:5px 9px;}
.bt-cut{border-top:3px dashed var(--tk-cut);margin:14px -20px 10px;}
.bt-item{font-size:21px;font-weight:700;line-height:1.2;}
.bt-sub{font-size:13px;color:var(--tk-muted);margin-top:2px;}
.bt-mod{font-size:17px;font-weight:700;padding-left:22px;margin-top:3px;}
.bt-mod::before{content:"» ";}
.bt-allergy{margin-top:6px;border:3px solid var(--tk-allergy);background:var(--tk-allergy-bg);color:var(--tk-allergy-ink);font-weight:700;font-size:16px;padding:5px 9px;}
</style>'''


# ====================================================================
# data helpers (read-only; all numbers come from the scheduler / database / Feature 3 alert passed in)
# ====================================================================
def _urgency(row, alert):
    """(label, css kind). Feature 3's timing already includes item-level delays the chef reported, so prefer it when available."""
    if alert:
        t = alert['timing']
        cat, late = t['category'], t['late_minutes']
    else:
        cat = 'blocked' if row['blocked'] else {'LATE': 'late', 'RISK': 'at_risk'}.get(row['urgency'], 'on_track')
        late = row['late_minutes'] or 0
    label, kind = {'blocked': ('Blocked', 'blocked'), 'late': (f'Late {late}m', 'late'), 'at_risk': ('At risk', 'risk'),
                   'unknown': ('No estimate', 'risk'), 'on_track': ('On track', 'ok')}[cat]
    return label, kind, cat, late


def _incident_text(row):
    parts = []
    for issue in row['matching_incidents']:
        bits = []
        if issue['ingredient']:
            bits.append('Unavailable: ' + issue['ingredient'])
        if issue['station']:
            bits.append(f"{issue['station']} delayed {issue['delay_minutes']} min")
        text = ', '.join(bits)
        if text and text not in parts:
            parts.append(text)
    return parts


def _refresh():
    """Re-draw just this workspace after selecting a tab. Falls back to a normal rerun if we are not inside a fragment rerun."""
    try:
        st.rerun(scope='fragment')
    except st.errors.StreamlitAPIException:
        st.rerun()


def _prep_minutes(row):
    return max((remaining_minutes(i) for i in row['items'] if i['status'] != 'ready'), default=0)


# ====================================================================
# UI SECTION: ONE TAB in the vertical rail (Jiena's compact ticket, adapted)
# ====================================================================
def tab_html(row, rank, selected, alert):
    e = html.escape
    label, kind, _, _ = _urgency(row, alert)
    color = TICKET_COLORS.get(row['source'], '#555')
    count = sum(i['quantity'] for i in row['items'])
    flag = '<div class="tk-flag">ALLERGY</div>' if any(i['allergy'] for i in row['items']) else ''
    return (f"<div class='tk-paper tk-tab{' sel' if selected else ''}' style='--src:{color}'>"
            f"<div class='tk-top'><span><span class='tk-rank'>{rank}</span><span class='tk-no'>#{e(str(row['id']))}</span></span>"
            f"<span class='tk-src'>{e(row['source'])}</span></div>"
            f"<div class='tk-row'><span class='tk-status'>{e(row['status'].replace('_', ' '))}</span><span class='tk-urg {kind}'>{e(label)}</span></div>"
            f"<div class='tk-sub'>DUE {e(clock(row['pickup_at']))} · {count} item{'s' if count != 1 else ''}</div>{flag}</div>")


# ====================================================================
# UI SECTION: THE OPENED TICKET (Jiena's big ticket, adapted) with working Start / Ready buttons
# ====================================================================
def render_detail(row, rank, total, alert, station_filter):
    e = html.escape
    color = TICKET_COLORS.get(row['source'], '#555')
    label, kind, cat, late = _urgency(row, alert)
    est = alert['revised_at'] if alert and alert['revised_at'] else row['predicted_at']
    est_text = 'Blocked' if row['blocked'] else ('None yet' if est is None else clock(est))
    slack = alert['timing']['slack'] if alert and alert['timing']['slack'] is not None else row['slack']
    why = {'blocked': 'Waiting on an unavailable ingredient, so no ready time can be promised.',
           'unknown': 'No ready time can be given until the kitchen reports one.',
           'late': f'Predicted {late} min past the promised time.',
           'at_risk': f'Only {slack} min of slack before the promised time.',
           'on_track': f'{slack} min of slack before the promised time.'}[cat]
    delays = _incident_text(row) + ([alert['headline']] if alert and alert['severity'] not in ('on_track',) else [])
    inject_css(f".st-key-tk_detail{{--bt-src:{color};}}")   # platform colour for the ticket's top strip (Jiena's approach)
    with st.container(key='tk_detail'):
        st.markdown(
            f"<div class='tk-paper' style='--bt-src:{color}'>"
            f"<div class='bt-head'><span class='bt-no'>#{e(str(row['id']))}</span><span class='bt-src'>{e(row['source'])}</span>"
            f"<span class='bt-chip {e(row['status'])}'>{e(row['status'].replace('_', ' '))}</span><span class='tk-urg {kind}'>{e(label)}</span></div>"
            f"<div class='bt-facts'><div><b>Received</b><span>{e(clock(row['received_at']))}</span></div>"
            f"<div><b>Promised ready</b><span>{e(clock(row['pickup_at']))}</span></div>"
            f"<div><b>Est. ready</b><span>{e(est_text)}</span></div>"
            f"<div><b>Est. prep</b><span>{_prep_minutes(row)} min</span></div>"
            f"<div><b>Priority</b><span>{rank} of {total}</span></div></div>"
            f"<div class='bt-why'>{e(why)} {e(row['recipient'])}.</div>"
            + ''.join(f"<div class='bt-delay'>Kitchen delay: {e(d)}</div>" for d in delays) + "</div>", unsafe_allow_html=True)
        st.markdown("<div class='bt-cut'></div>", unsafe_allow_html=True)
        shown = [i for i in row['items'] if station_filter == 'All stations' or i['station'] == station_filter]
        if not shown:
            st.caption(f'No items for {station_filter} on this order.')
        for it in shown:
            text, start, ready = st.columns([3.2, 1.7, 2.0], vertical_alignment='center')
            text.markdown(
                f"<div class='tk-paper'><div class='bt-item'>{it['quantity']} × {e(it['name'])}"
                f" <span class='bt-chip {e(it['status'])}'>{e(it['status'])}</span></div>"
                f"<div class='bt-sub'>{e(it['station'])} · {it['prep_minutes']} min</div>"
                + (f"<div class='bt-mod'>{e(it['modifier'])}</div>" if it['modifier'] else '')
                + (f"<div class='bt-allergy'>ALLERGY: {e(it['allergy'])}</div>" if it['allergy'] else '') + '</div>', unsafe_allow_html=True)
            if start.button('Start Prep', key=f"tk_start_{it['id']}", disabled=it['status'] != 'queued', use_container_width=True):
                update_item(it['id'], 'cooking')
                st.rerun()
            if ready.button('Mark Ready', key=f"tk_ready_{it['id']}", disabled=it['status'] == 'ready', type='primary', use_container_width=True):
                update_item(it['id'], 'ready')
                st.rerun()


# ====================================================================
# UI SECTION: THE WORKSPACE (station filter + counts + [rail | selected ticket]), refreshes itself
# ====================================================================
def render_ticket_workspace(alerts_fn=None, stations=()):
    """alerts_fn: optional zero-arg callable returning {order_id: alert} (Feature 3's order_alerts) for revised ETAs / delay messages."""
    inject_css(CSS)
    st.markdown('#### Kitchen Tickets')
    pick, help_col = st.columns([4, 1.5], vertical_alignment='bottom')
    station_filter = pick.selectbox('Cooking station', ['All stations'] + list(stations), key='tk_station')
    with help_col.popover('Help'):
        st.caption('Tickets are ranked by deadline risk (estimated latest start), not arrival order. Each station cooks one ticket line at a time in this demo. '
                   'Click a ticket tab to open it.')

    @st.fragment(run_every='5s')
    def live():
        orders = fetch_orders()
        ranked = schedule(orders, fetch_incidents())
        alerts = alerts_fn() if alerts_fn else {}
        late = sum(r['urgency'] in ('RISK', 'LATE') for r in ranked)
        blocked = sum(r['blocked'] for r in ranked)
        st.markdown(f"**{len(ranked)}** open · **{late}** at risk / late · **{blocked}** blocked")
        hints = [(s, n, c) for s, n, c in batch_hints(orders) if station_filter in ('All stations', s)]
        if hints:
            with st.expander(f'Batching hints ({len(hints)})'):
                for s, n, c in hints:
                    st.caption(f'{c}× {n} needed at {s}')
        if not ranked:
            st.caption('No open orders.')
            return
        ids = [str(r['id']) for r in ranked]
        sel = st.session_state.get(SELECTED)
        if sel is None or str(sel) not in ids:   # nothing chosen yet, or that order is done: fall back to the top-priority ticket
            sel = ids[0]
        sel = str(sel)
        with st.container(key='tk_layout'):
            rail, detail = st.columns([3, 7], gap='small')
            with rail, st.container(key='tk_rail'):
                for rank, r in enumerate(ranked, start=1):
                    is_sel = str(r['id']) == sel
                    with st.container(key=f"tk_tab_{r['id']}"):
                        st.markdown(tab_html(r, rank, is_sel, alerts.get(r['id'])), unsafe_allow_html=True)
                        # invisible button stretched over the tab (CSS above) so the whole tab is one big touch target — Jiena's trick
                        if st.button(f"Open ticket #{r['id']}", key=f"tk_open_{r['id']}"):
                            st.session_state[SELECTED] = str(r['id'])
                            _refresh()
            with detail:
                row = next(r for r in ranked if str(r['id']) == sel)
                render_detail(row, ids.index(sel) + 1, len(ranked), alerts.get(row['id']), station_filter)

    live()
