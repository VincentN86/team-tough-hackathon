"""Feature 1: simulated intake UI and read-only dashboard helpers.

The existing recipient column holds either a legacy handoff category or
"Name · Handoff category". No schema or downstream status changes are needed.
"""
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import escape
import sqlite3

import streamlit as st

from database import MENU, SOURCES, RECIPIENTS, create_order, fetch_orders


STATUS_LABELS = {
    'queued': 'Queued', 'cooking': 'Cooking', 'ready_to_pack': 'Ready to pack',
    'packed': 'Packed', 'handed_off': 'Handed off',
}
SOURCE_COLORS = {
    'DoorDash': ('#fff0ed', '#a32716'),
    'Uber Eats': ('#e1f5e9', '#145b35'),
    'In-person POS': ('#e8efff', '#2447a5'),
    'Website': ('#f0eaff', '#6332a0'),
    'Phone': ('#fff3d6', '#805400'),
}
STATUS_COLORS = {
    'queued': ('#e8efff', '#2447a5'),
    'cooking': ('#fff3d6', '#805400'),
    'ready_to_pack': ('#f0eaff', '#6332a0'),
    'packed': ('#e1f5e9', '#145b35'),
    'handed_off': ('#edf0f3', '#465160'),
}
SORT_OPTIONS = ['Newest first', 'Oldest first', 'Pickup deadline']


def filter_orders(orders, source='All Sources', status='All statuses', query='',
                  sort='Newest first'):
    """Return a sorted view without changing records consumed by other tabs."""
    query = query.strip().casefold()
    matches = [o for o in orders
               if (source == 'All Sources' or o['source'] == source)
               and (status == 'All statuses' or o['status'] == status)
               and (not query or query.lstrip('#') in str(o['id']).casefold()
                    or query in o['recipient'].casefold())]
    field = 'pickup_at' if sort == 'Pickup deadline' else 'received_at'
    return sorted(matches, key=lambda o: (datetime.fromisoformat(o[field]), str(o['id'])),
                  reverse=sort == 'Newest first')


def summarize_orders(orders):
    statuses = Counter(o['status'] for o in orders)
    return {'total': len(orders),
            'active': sum(o['status'] != 'handed_off' for o in orders),
            'statuses': statuses, 'sources': Counter(o['source'] for o in orders)}


def recipient_label(name, handoff):
    name = name.strip()
    if not name or len(name) > 80 or any(ord(c) < 32 for c in name):
        raise ValueError('Enter a recipient name of 1–80 characters on one line.')
    if handoff not in RECIPIENTS:
        raise ValueError('Choose a supported handoff type.')
    return f'{name} · {handoff}'


def badge(text, colors):
    background, foreground = colors
    return (f'<span class="rr-badge" style="background:{background};color:{foreground}">'
            f'<span class="rr-dot" aria-hidden="true"></span>{escape(str(text))}</span>')


def order_card(order):
    """Escape every database value used in HTML, including names and notes."""
    def local_time(value):
        return datetime.fromisoformat(value).astimezone().strftime('%b %d · %I:%M %p')

    source = badge(order['source'], SOURCE_COLORS.get(order['source'], ('#edf0f3', '#465160')))
    status = badge(STATUS_LABELS.get(order['status'], order['status']),
                   STATUS_COLORS.get(order['status'], ('#edf0f3', '#465160')))
    items = ''.join(
        f'<span class="rr-item"><strong class="rr-quantity">{escape(str(item["quantity"]))}×</strong>'
        f'<span>{escape(item["name"])}</span></span>' for item in order['items'])
    notes = []
    for item in order['items']:
        for field, label in [('modifier', 'Modification'), ('allergy', 'Allergy — staff must verify')]:
            if item[field].strip():
                notes.append(f'<div class="rr-note rr-{field}"><strong>{label}</strong>'
                             f'<span>{escape(item["name"])} — {escape(item[field])}</span></div>')
    return (
        '<article class="rr-order">'
        '<div class="rr-order-top"><div class="rr-order-identity">'
        f'<strong class="rr-id">#{escape(str(order["id"]))}</strong>{source}{status}</div>'
        f'<div class="rr-times"><div><span class="rr-label">Received</span>{local_time(order["received_at"])}</div>'
        f'<div class="rr-pickup"><span class="rr-label">Pickup deadline</span>'
        f'<strong>{local_time(order["pickup_at"])}</strong></div></div></div>'
        f'<div class="rr-recipient"><span class="rr-label">Recipient / handoff</span>{escape(order["recipient"])}</div>'
        f'<div class="rr-items"><span class="rr-label">Order items</span><div class="rr-item-list">{items}</div></div>'
        f'{"".join(notes)}</article>'
    )


def clear_filters():
    st.session_state['intake_source'] = 'All Sources'
    st.session_state['intake_status'] = 'All statuses'
    st.session_state['intake_search'] = ''
    st.session_state['intake_sort'] = 'Newest first'


def render_order_form():
    # This form is outside the timed fragment. A successful submission is latched
    # until staff explicitly start another order, preventing queued double clicks.
    created = st.session_state.get('intake_created')
    if created:
        with st.container(border=True, key='intake_confirmation'):
            message, action = st.columns([4, 1], vertical_alignment='center')
            message.success(f'Order #{created} saved. It is available in Cook, Packer, and Front Desk.', icon='✅')
            if action.button('Start another order', key='intake_another', use_container_width=True):
                st.session_state.pop('intake_created', None)
                st.session_state['intake_draft'] = st.session_state.get('intake_draft', 0) + 1
                st.rerun()
        return

    with st.expander('＋ Add / Simulate Order'):
        st.caption('Create a fictional incoming order. No external platform API is connected.')
        draft = st.session_state.get('intake_draft', 0)
        with st.form(f'intake_new_order_{draft}'):
            st.markdown('<div class="rr-section-title"><span>01</span> Order &amp; pickup details</div>', unsafe_allow_html=True)
            a, b = st.columns(2)
            source = a.selectbox('Order source', SOURCES)
            name = b.text_input('Recipient name', max_chars=80, placeholder='e.g. Alex Chen')
            a, b = st.columns(2)
            handoff = a.selectbox('Handoff to', RECIPIENTS, index=1)
            minutes = b.number_input('Pickup in minutes', min_value=5, max_value=90, value=25, step=1)
            st.divider()
            st.markdown('<div class="rr-section-title"><span>02</span> Menu &amp; special instructions</div>', unsafe_allow_html=True)
            st.caption('Choose quantities below · 0 = not ordered · Each note applies only to its item.')
            lines = []
            for food in MENU:
                qty_col, mod_col, allergy_col = st.columns([1.2, 2, 2], vertical_alignment='bottom')
                qty = qty_col.number_input(food, min_value=0, max_value=8, value=0, step=1,
                                           key=f'intake_{draft}_{food}_qty')
                mod = mod_col.text_input(f'{food} modification', max_chars=200,
                                         placeholder='Optional', key=f'intake_{draft}_{food}_mod')
                allergy = allergy_col.text_input(f'{food} allergy instruction', max_chars=200,
                                                 placeholder='Optional', key=f'intake_{draft}_{food}_allergy')
                if qty:
                    lines.append((food, qty, mod.strip(), allergy.strip()))
            st.divider()
            submitted = st.form_submit_button('Create incoming order', type='primary', use_container_width=True)
            st.caption('After saving, filters clear so your new order is visible. Start another order to create a second one.')
        if submitted and not st.session_state.get('intake_created'):
            try:
                recipient = recipient_label(name, handoff)
                if not lines:
                    raise ValueError('Choose at least one item by setting its quantity above 0.')
                new_id = create_order(source, recipient, minutes, lines)
            except ValueError as exc:
                st.warning(str(exc))
            except sqlite3.Error:
                st.error('The order could not be saved. Your inputs are kept; please try again.')
            else:
                st.session_state['intake_created'] = new_id
                clear_filters()
                st.rerun()


@st.fragment(run_every='5s')
def render_feed():
    orders = fetch_orders()
    summary = summarize_orders(orders)
    counts = summary['statuses']
    # Display-only deadline summary; this does not change kitchen priority or statuses.
    soon = datetime.now(timezone.utc) + timedelta(minutes=10)
    due = sum(o['status'] != 'handed_off' and datetime.fromisoformat(o['pickup_at']) <= soon
              for o in orders)
    kpis = [
        ('Total orders', summary['total'], 'Across all five channels', 'neutral'),
        ('Active orders', summary['active'], f"{counts['queued']} queued · {counts['cooking']} cooking", 'active'),
        ('Ready orders', counts['ready_to_pack'] + counts['packed'],
         f"{counts['ready_to_pack']} ready to pack · {counts['packed']} packed", 'ready'),
        ('Pickup soon', due, 'Due within 10 min or overdue · not handed off', 'due'),
    ]
    st.markdown('<div class="rr-kpis">' + ''.join(
        f'<div class="rr-kpi rr-kpi-{tone}"><div class="rr-kpi-label">{label}</div>'
        f'<div class="rr-kpi-value">{value}</div><div class="rr-kpi-detail">{detail}</div></div>'
        for label, value, detail, tone in kpis
    ) + '</div>', unsafe_allow_html=True)
    with st.container(border=True, key='intake_controls'):
        st.markdown('<div class="rr-control-title">Channels <span>All orders, by source</span></div>'
                    '<div class="rr-sources">' + ' '.join(
            badge(f'{source} · {summary["sources"][source]}', SOURCE_COLORS[source]) for source in SOURCES
        ) + '</div>', unsafe_allow_html=True)
        search, source, status, sort = st.columns([2, 1.3, 1.3, 1.3])
        query = search.text_input('Search orders', placeholder='Search ID or recipient…', key='intake_search')
        selected_source = source.selectbox('Source', ['All Sources'] + SOURCES, key='intake_source')
        selected_status = status.selectbox('Status', ['All statuses'] + list(STATUS_LABELS),
                                           format_func=lambda s: STATUS_LABELS.get(s, s), key='intake_status')
        selected_sort = sort.selectbox('Sort by', SORT_OPTIONS, key='intake_sort')
        visible = filter_orders(orders, selected_source, selected_status, query, selected_sort)
        help_text, reset = st.columns([5, 1], vertical_alignment='center')
        help_text.caption('Search by order ID or recipient · Combine filters to narrow the queue')
        reset.button('Clear filters', on_click=clear_filters, key='intake_clear', use_container_width=True)
    caption, reset = st.columns([5, 1])
    caption.markdown(f'<div class="rr-feed-title">Order queue <span>{len(visible)} of {len(orders)} orders</span></div>', unsafe_allow_html=True)
    reset.markdown('<div class="rr-refresh"><span class="rr-dot"></span> Auto-refresh · 5s</div>', unsafe_allow_html=True)
    st.caption(f"Times are server-local · {counts['handed_off']} handed off · Summary counts include all sources")
    if not orders:
        st.info('No orders yet. Open Add / Simulate Order to create your first order.')
    elif not visible:
        st.info('No orders match your filters. Try another source, status, or search term.')
    for order in visible:
        st.markdown(order_card(order), unsafe_allow_html=True)


def render_intake():
    st.markdown('''<style>
    /* Only our markup and explicitly keyed intake containers are styled. */
    .st-key-intake_shell {--rr-accent:#087f75;--rr-border:#8995a330;
        --rr-muted:color-mix(in srgb, var(--text-color, #172b36) 65%, transparent);}
    .rr-hero {display:flex;align-items:center;justify-content:space-between;gap:20px;
        padding:24px 28px;margin:12px 0 6px;border:1px solid var(--rr-border);
        border-left:5px solid var(--rr-accent);border-radius:16px;
        background:linear-gradient(115deg,#087f7510,transparent);}
    .rr-eyebrow {color:var(--rr-accent);font-size:11px;font-weight:750;letter-spacing:1.6px;text-transform:uppercase;}
    .rr-hero h2 {font-size:28px;letter-spacing:-.8px;padding:7px 0 6px;margin:0;line-height:1.25;}
    .rr-hero p {color:var(--rr-muted);font-size:14px;margin:0;line-height:1.6;}
    .rr-demo {white-space:nowrap;background:#087f7512;color:var(--rr-accent);border:1px solid #087f7530;
        padding:7px 12px;border-radius:100px;font-size:11px;font-weight:700;letter-spacing:.4px;}
    .rr-kpis {display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:14px 0 8px;}
    .rr-kpi {background:var(--background-color,#fff);border:1px solid var(--rr-border);border-radius:14px;
        padding:18px 20px;box-shadow:0 3px 12px #142b3910;border-top:3px solid #8995a370;}
    .rr-kpi-active,.rr-kpi-ready {border-top-color:var(--rr-accent);}
    .rr-kpi-due {border-top-color:#d79b42;}
    .rr-kpi-label {font-size:12px;font-weight:650;color:var(--rr-muted);}
    .rr-kpi-value {font-size:34px;font-weight:750;letter-spacing:-1px;line-height:1.4;font-variant-numeric:tabular-nums;}
    .rr-kpi-detail {font-size:11px;color:var(--rr-muted);line-height:1.6;}
    .st-key-intake_controls {background:var(--secondary-background-color,#f6f8fa);border-radius:14px;}
    .rr-control-title {font-size:13px;font-weight:700;}
    .rr-control-title>span {font-size:11px;color:var(--rr-muted);font-weight:400;margin-left:10px;}
    .rr-sources {display:flex;flex-wrap:wrap;gap:8px;margin-top:12px;}
    .rr-badge {display:inline-flex;align-items:center;gap:6px;border-radius:100px;padding:5px 10px;
        font-size:11px;font-weight:700;white-space:nowrap;line-height:1.5;border:1px solid #00000008;}
    .rr-dot {display:inline-block;width:5px;height:5px;flex-shrink:0;border-radius:50%;background:currentColor;}
    .rr-feed-title {font-size:18px;font-weight:700;margin-top:12px;letter-spacing:-.3px;}
    .rr-feed-title>span {font-size:12px;font-weight:400;color:var(--rr-muted);margin-left:12px;letter-spacing:0;}
    .rr-refresh {font-size:11px;color:var(--rr-accent);text-align:right;margin-top:17px;white-space:nowrap;}
    .rr-order {border:1px solid var(--rr-border);border-radius:14px;padding:18px 22px;margin-bottom:4px;
        background:var(--background-color,#fff);color:var(--text-color,#172b36);box-shadow:0 2px 8px #142b3908;}
    .rr-order-top {display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap;}
    .rr-order-identity {display:flex;align-items:center;flex-wrap:wrap;gap:8px;}
    .rr-id {font-size:20px;letter-spacing:-.5px;margin-right:6px;font-variant-numeric:tabular-nums;}
    .rr-label {display:block;color:var(--rr-muted);font-size:10px;font-weight:650;
        text-transform:uppercase;letter-spacing:.7px;margin-bottom:4px;}
    .rr-recipient {font-size:14px;font-weight:600;margin-top:14px;overflow-wrap:anywhere;}
    .rr-times {display:flex;flex-wrap:wrap;gap:12px 22px;font-size:12px;font-variant-numeric:tabular-nums;}
    .rr-times>div {padding-left:12px;border-left:1px solid var(--rr-border);}
    .rr-pickup strong {font-weight:650;}
    .rr-items {border-top:1px solid var(--rr-border);padding-top:12px;margin-top:12px;}
    .rr-item-list {display:flex;flex-wrap:wrap;gap:8px 20px;margin-top:7px;}
    .rr-item {display:inline-flex;align-items:center;gap:8px;font-size:13px;}
    .rr-quantity {display:inline-flex;align-items:center;justify-content:center;border-radius:6px;
        background:#087f7512;color:var(--rr-accent);min-width:29px;padding:3px 5px;font-size:12px;}
    .rr-note {display:flex;flex-wrap:wrap;gap:4px 12px;margin-top:10px;padding:9px 12px;border-radius:7px;
        font-size:12px;line-height:1.6;white-space:pre-wrap;overflow-wrap:anywhere;}
    .rr-note strong {font-size:11px;}
    .rr-modifier {background:var(--secondary-background-color,#f5f7fa);border-left:3px solid #8995a370;}
    .rr-allergy {background:#fff3df;color:#79420c;border-left:3px solid #d79732;}
    .rr-section-title {font-size:15px;font-weight:650;margin:6px 0 14px;}
    .rr-section-title>span {display:inline-block;font-size:11px;color:var(--rr-accent);background:#087f7512;
        padding:5px 8px;border-radius:6px;margin-right:8px;}
    .st-key-intake_confirmation {background:#087f7508;border-radius:14px;}
    .st-key-intake_shell [data-testid="stBaseButton-primary"] {background:#087f75;border-color:#087f75;color:#fff;}
    .st-key-intake_shell [data-testid="stBaseButton-primary"]:hover {background:#06685f;border-color:#06685f;}
    @media(max-width:900px) {.rr-kpis {grid-template-columns:repeat(2,minmax(0,1fr));}
        .rr-hero {padding:20px;}.rr-hero h2 {font-size:24px;}}
    @media(max-width:540px) {.rr-hero {align-items:flex-start;flex-direction:column;gap:12px;}
        .rr-kpi {padding:14px;}.rr-order {padding:16px;}.rr-times {margin-top:4px;}
        .rr-times>div {padding-left:0;border:0;}.rr-refresh {white-space:normal;}}
    </style>''', unsafe_allow_html=True)
    with st.container(key='intake_shell'):
        st.markdown('<header class="rr-hero"><div><div class="rr-eyebrow">RushReady · Restaurant operations</div>'
                    '<h2>Unified Order Intake</h2><p>Every channel, one queue. Keep incoming orders and pickups in clear view.</p>'
                    '</div><span class="rr-demo">SIMULATED ORDER FEED</span></header>', unsafe_allow_html=True)
        render_order_form()
        render_feed()
