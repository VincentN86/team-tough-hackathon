"""Individual kitchen tickets retained from main; uses the shared SQLite workflow."""
from datetime import datetime
import html
import streamlit as st
from database import fetch_orders, update_item

TICKET_COLORS={'DoorDash':'#e8320b','Uber Eats':'#05a357','Website':'#7c4ddb','Phone':'#2563eb','In-person POS':'#444'}

def clock(t):
    return datetime.fromisoformat(t).astimezone().strftime('%I:%M %p').lstrip('0')

def ticket_html(o,compact=False,selected=False):
    """One order as a paper kitchen ticket. compact=True is the small rail tab; selected marks the open ticket."""
    e=html.escape
    lines=[]
    for i in o['items']:
        lines.append(f"<div class='t-item'>{e(str(i['quantity']))} × {e(i['name'])}</div>")
        if i['modifier']:
            lines.append(f"<div class='t-mod'>{e(i['modifier'])}</div>")
    allergies=[f"{e(i['name'])}: {e(i['allergy'])}" for i in o['items'] if i['allergy']]
    allergy_box=f"<div class='t-allergy'>⚠ ALLERGY<br>{'<br>'.join(allergies)}</div>" if allergies else ''
    color=TICKET_COLORS.get(o['source'],'#555')
    head=(f"<div class='t-top'><span class='t-no'>#{e(str(o['id']))}</span><span class='t-src'>{e(o['source'])}</span></div>"
          f"<div class='t-top'><span class='t-status'>{e(o['status'].replace('_',' '))}</span>"
          f"<span class='t-due'>DUE {e(clock(o['pickup_at']))}</span></div>")
    if compact:
        count=sum(i['quantity'] for i in o['items'])
        flag="<div class='t-flag'>⚠ ALLERGY</div>" if allergies else ''
        return (f"<div class='ticket tab' style='--src:{color}'>{head}<div class='t-cut'></div>"
                f"<div class='t-summary'>{count} item{'s' if count!=1 else ''} · {e(o['recipient'])}</div>{flag}</div>")
    opened="<div class='t-top'><span class='t-open'>OPEN ▸</span></div>" if selected else ''
    return (f"<div class='ticket{' open' if selected else ''}' style='--src:{color}'>{opened}{head}"
            f"<div class='t-meta'>{e(o['recipient'])} · In {e(clock(o['received_at']))}</div>"
            f"<div class='t-cut'></div>{''.join(lines)}{allergy_box}</div>")

def opened_ticket():
    open_id=st.session_state.get('open_ticket')
    if not open_id:
        return
    o=next((x for x in fetch_orders() if str(x['id'])==str(open_id)),None)
    if o is None:
        st.session_state.pop('open_ticket',None)
        return
    e=html.escape
    color=TICKET_COLORS.get(o['source'],'#555')
    st.markdown(f"<style>.st-key-big_ticket{{--bt-src:{color};}}</style>",unsafe_allow_html=True)
    with st.container(key='big_ticket'):
        top,close=st.columns([6,1],vertical_alignment='top')
        top.markdown(f"<div><span class='bt-no'>#{e(str(o['id']))}</span><span class='bt-src'>{e(o['source'])}</span>"
                     f"<span class='bt-chip'>{e(o['status'].replace('_',' '))}</span></div>"
                     f"<div class='bt-meta'>{e(o['recipient'])} · In <b>{e(clock(o['received_at']))}</b> · "
                     f"DUE <b>{e(clock(o['pickup_at']))}</b></div>",unsafe_allow_html=True)
        if close.button('✕ Close',key='close_ticket',use_container_width=True):
            st.session_state.pop('open_ticket',None)
            st.rerun()
        st.markdown("<div class='bt-cut'></div>",unsafe_allow_html=True)
        for it in o['items']:
            text,start,ready=st.columns([5,1.3,1.3],vertical_alignment='center')
            text.markdown(f"<div class='bt-item'>{e(str(it['quantity']))} × {e(it['name'])}"
                          f"<span class='bt-chip {e(it['status'])}'>{e(it['status'])}</span></div>"
                          f"<div class='bt-sub'>{e(it['station'])} · {e(str(it['prep_minutes']))} min</div>"
                          +(f"<div class='bt-mod'>{e(it['modifier'])}</div>" if it['modifier'] else '')
                          +(f"<div class='bt-allergy'>⚠ ALLERGY: {e(it['allergy'])}</div>" if it['allergy'] else ''),
                          unsafe_allow_html=True)
            if start.button('Start',key=f"bt_start_{it['id']}",disabled=it['status']!='queued',use_container_width=True):
                update_item(it['id'],'cooking');st.rerun()
            if ready.button('✓ Ready',key=f"bt_ready_{it['id']}",disabled=it['status']=='ready',use_container_width=True):
                update_item(it['id'],'ready');st.rerun()
    st.write('')


def pick_ticket():
    st.session_state['open_ticket'] = st.session_state.get('kitchen_ticket_picker')


def render_tickets():
    orders = fetch_orders()
    st.markdown('<style>' + TICKET_CSS + '</style>', unsafe_allow_html=True)
    st.selectbox('Open kitchen ticket', [o['id'] for o in reversed(orders)], index=None,
                 format_func=lambda value: f'Order #{value}', key='kitchen_ticket_picker',
                 on_change=pick_ticket, placeholder='Select an order')
    opened_ticket()

TICKET_CSS = '.st-key-big_ticket{background:#fffdf4;color:#1d1d1d;font-family:"Courier New",Courier,monospace;\n  padding:26px 34px 52px;min-height:68vh;border-top:14px solid var(--bt-src,#555);\n  -webkit-mask:conic-gradient(from -45deg at bottom,#0000,#000 1deg 89deg,#0000 90deg) 50%/22px 100%;\n          mask:conic-gradient(from -45deg at bottom,#0000,#000 1deg 89deg,#0000 90deg) 50%/22px 100%;}\n.st-key-big_ticket [data-testid="stMarkdownContainer"]{color:#1d1d1d;font-family:inherit;}\n.st-key-big_ticket button{background:#fff;color:#1d1d1d;border:2px solid #1d1d1d;font-family:inherit;font-weight:700;min-height:3.2rem;}\n.st-key-big_ticket button:hover{background:#1d1d1d;color:#fffdf4;border-color:#1d1d1d;}\n.st-key-big_ticket button:disabled{background:transparent;color:#9a958a;border-color:#cfc9ba;}\n.bt-no{font-size:56px;font-weight:700;letter-spacing:2px;line-height:1;}\n.bt-src{display:inline-block;font-size:16px;font-weight:700;text-transform:uppercase;color:#fff;background:var(--bt-src,#555);padding:4px 10px;border-radius:4px;vertical-align:middle;margin-left:14px;}\n.bt-meta{font-size:17px;color:#555;margin-top:10px;}\n.bt-meta b{color:#1d1d1d;}\n.bt-cut{border-top:3px dashed #b9b2a0;margin:18px -34px 14px;}\n.bt-item{font-size:28px;font-weight:700;line-height:1.2;}\n.bt-sub{font-size:15px;color:#555;margin-top:2px;}\n.bt-mod{font-size:21px;padding-left:28px;margin-top:4px;}\n.bt-mod::before{content:"» ";}\n.bt-chip{display:inline-block;font-size:13px;font-weight:700;text-transform:uppercase;border:2px solid #1d1d1d;padding:1px 7px;margin-left:10px;vertical-align:middle;}\n.bt-chip.cooking{background:#ffd23f;}\n.bt-chip.ready{background:#2fbf71;border-color:#1a7a46;}\n.bt-allergy{margin-top:6px;border:3px solid #c0157a;background:#ffe3f2;color:#8a0050;font-weight:700;font-size:19px;padding:6px 10px;}\n'
