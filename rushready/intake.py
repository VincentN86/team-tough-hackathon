"""BREADY Dispatch: isolated intake UI, using the shared order contract."""
from collections import Counter
from datetime import datetime, timezone
from html import escape
import math
from pathlib import Path
import sqlite3

import streamlit as st
from database import MENU, SOURCES, RECIPIENTS, create_order, fetch_orders

STATUS_LABELS = {
    'queued': 'Queued', 'cooking': 'In kitchen', 'ready_to_pack': 'Ready to pack',
    'packed': 'Packed', 'handed_off': 'Completed',
}
STATUS_GROUPS = {
    'All': None, 'Queued': ('queued',), 'In progress': ('cooking',),
    'Ready': ('ready_to_pack', 'packed'), 'Completed': ('handed_off',),
}
SOURCE_MARKS = {'DoorDash': 'DD', 'Uber Eats': 'UE', 'In-person POS': 'POS',
                'Website': 'WEB', 'Phone': 'TEL'}
SORT_OPTIONS = ['Newest first', 'Oldest first', 'Pickup deadline']


def timestamp(value):
    dt = datetime.fromisoformat(value)
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def filter_orders(orders, source='All Sources', status='All statuses', query='',
                  sort='Newest first'):
    """Accept display groups and legacy exact statuses; never mutate records."""
    query = query.strip().casefold()
    statuses = STATUS_GROUPS.get(status, (status,))
    if status == 'All statuses':
        statuses = None
    matches = [o for o in orders
               if (source == 'All Sources' or o['source'] == source)
               and (statuses is None or o['status'] in statuses)
               and (not query or query.lstrip('#') in str(o['id']).casefold()
                    or query in o['recipient'].casefold())]
    field = 'pickup_at' if sort == 'Pickup deadline' else 'received_at'
    return sorted(matches, key=lambda o: (timestamp(o[field]), str(o['id'])),
                  reverse=sort == 'Newest first')


def summarize_orders(orders):
    return {'total': len(orders),
            'active': sum(o['status'] != 'handed_off' for o in orders),
            'statuses': Counter(o['status'] for o in orders),
            'sources': Counter(o['source'] for o in orders)}


def pickup_state(order, now=None):
    """Deadline attention is independent of workflow progress."""
    if order['status'] == 'handed_off':
        return 'Handed off', 'quiet'
    seconds = (timestamp(order['pickup_at']) - (now or datetime.now(timezone.utc))).total_seconds()
    if seconds < 0:
        return f'Overdue {max(1, math.ceil(-seconds / 60))}m', 'overdue'
    minutes = math.ceil(seconds / 60)
    return ('Due now' if minutes == 0 else f'Pickup in {minutes}m',
            'soon' if seconds <= 600 else 'quiet')


def recipient_label(name, handoff):
    name = name.strip()
    if not name or len(name) > 80 or any(ord(c) < 32 for c in name):
        raise ValueError('Enter a recipient name of 1–80 characters on one line.')
    if handoff not in RECIPIENTS:
        raise ValueError('Choose a supported handoff type.')
    return f'{name} · {handoff}'


def choose_selection(orders, selected_id):
    """Keep selection by ID, including when newer rows arrive or filters change."""
    return next((o for o in orders if o['id'] == selected_id), orders[0] if orders else None)


def ticket_html(order):
    def local_time(value):
        return timestamp(value).astimezone().strftime('%b %d, %I:%M %p')

    deadline, tone = pickup_state(order)
    ready = 'ready' if order['status'] in ('ready_to_pack', 'packed') else ''
    lines = []
    for item in order['items']:
        notes = ''
        for field, label in [('modifier', 'Modification'), ('allergy', 'Allergy · staff verification required')]:
            if item[field].strip():
                notes += (f'<div class="dispatch-note {field}"><b>{label}</b>'
                          f'<span>{escape(item[field])}</span></div>')
        lines.append(f'<div class="dispatch-line"><div class="dispatch-food">'
                     f'<b class="dispatch-qty">{escape(str(item["quantity"]))}×</b>'
                     f'<b>{escape(item["name"])}</b></div>{notes}</div>')
    return (
        '<article class="dispatch-ticket"><div class="dispatch-eyebrow">Selected ticket</div>'
        f'<div class="dispatch-ticket-heading"><h3>#{escape(str(order["id"]))}</h3>'
        f'<span class="dispatch-state {ready}">{escape(STATUS_LABELS.get(order["status"], order["status"]))}</span></div>'
        f'<div class="dispatch-channel"><span>{escape(SOURCE_MARKS.get(order["source"], "—"))}</span> {escape(order["source"])}</div>'
        f'<div class="dispatch-recipient">{escape(order["recipient"])}</div>'
        f'<div class="dispatch-deadline {tone}">{deadline}</div>'
        f'<dl class="dispatch-times"><div><dt>Received</dt><dd>{local_time(order["received_at"])}</dd></div>'
        f'<div><dt>Pickup deadline</dt><dd>{local_time(order["pickup_at"])}</dd></div></dl>'
        f'<div class="dispatch-eyebrow dispatch-items-label">Items · {sum(i["quantity"] for i in order["items"])}</div>'
        f'{"".join(lines)}<footer>Times shown in server-local time</footer></article>'
    )


def queue_row_label(order):
    """Six text paragraphs in a single native button; user text cannot add links."""
    def plain(value):
        value = ' '.join(str(value).split())
        for char in r'\`*_{}[]<>()#+-.!|':
            value = value.replace(char, '\\' + char)
        return value
    fields = [f'#{order["id"]}', order['source'], order['recipient'],
              ' · '.join(f'{i["quantity"]}× {i["name"]}' for i in order['items']),
              STATUS_LABELS.get(order['status'], order['status']), pickup_state(order)[0]]
    return '\n\n'.join(plain(field) for field in fields)


def clear_filters():
    st.session_state['dispatch_source'] = 'All Sources'
    st.session_state['dispatch_status'] = 'All'
    st.session_state['dispatch_search'] = ''
    st.session_state['dispatch_sort'] = 'Newest first'


def show_created():
    clear_filters()
    select_order(st.session_state['dispatch_created'])


def select_order(order_id):
    st.session_state['dispatch_selected'] = order_id
    st.session_state['dispatch_modal'] = 'details'


def close_order_dialog():
    st.session_state.pop('dispatch_modal', None)


def render_order_details():
    order = next((o for o in fetch_orders()
                  if o['id'] == st.session_state.get('dispatch_selected')), None)
    with st.container(key='dispatch_dialog'):
        if order is None:
            st.info('This order is no longer available.')
        else:
            st.markdown(ticket_html(order), unsafe_allow_html=True)
        if st.button('Back to orders', use_container_width=True):
            close_order_dialog()
            st.rerun()


def prepare_order(draft):
    recipient = recipient_label(draft['name'], draft['handoff'])
    if draft['source'] not in SOURCES:
        raise ValueError('Choose an order source.')
    if not draft['foods']:
        raise ValueError('Add at least one menu item.')
    lines = []
    for food in draft['foods']:
        item = draft['items'][food]
        if food not in MENU or not 1 <= item['quantity'] <= 8:
            raise ValueError('Choose a quantity between 1 and 8 for each item.')
        lines.append((food, item['quantity'], item['modifier'].strip(), item['allergy'].strip()))
    if not 5 <= draft['minutes'] <= 90:
        raise ValueError('Pickup must be between 5 and 90 minutes from now.')
    return (draft['source'], recipient, draft['minutes'], lines)


def review_draft():
    draft = st.session_state['dispatch_draft']
    for field in ('source', 'name', 'handoff', 'foods', 'minutes'):
        draft[field] = st.session_state.get(f'dispatch_draft_{field}', draft[field])
    for food in draft['foods']:
        item = draft['items'].setdefault(food, {'quantity': 1, 'modifier': '', 'allergy': ''})
        for field, prefix in [('quantity', 'qty'), ('modifier', 'mod'), ('allergy', 'allergy')]:
            item[field] = st.session_state.get(f'dispatch_draft_{prefix}_{food}', item[field])
    try:
        draft['review'] = prepare_order(draft)
        draft.pop('error', None)
    except ValueError as exc:
        draft['error'] = str(exc)


def edit_draft():
    st.session_state['dispatch_draft'].pop('review', None)


def render_creation():
    """Editable draft and explicit review. Timed feed never executes this code."""
    draft = st.session_state.setdefault('dispatch_draft', {
        'source': 'Website', 'name': '', 'handoff': 'Pickup customer',
        'foods': [], 'items': {}, 'minutes': 25,
    })
    # A queued second click cannot create again, even before the dialog closes.
    if draft.get('saved'):
        st.success(f'Order #{draft["saved"]} created.')
        return
    with st.container(key='dispatch_dialog'):
        st.caption('Simulate an incoming order. No external platform is connected.')
        if draft.get('review'):
            source, recipient, minutes, lines = draft['review']
            st.markdown('#### Review order')
            st.text(f'{source} · {recipient}')
            for food, qty, modifier, allergy in lines:
                st.text(f'{qty}× {food}')
                if modifier:
                    st.text('Modification: ' + modifier)
                if allergy:
                    st.warning('Allergy: ' + allergy)
            st.caption(f'Pickup {minutes} minutes after creation')
            back, save = st.columns([1, 2])
            back.button('Back to edit', use_container_width=True, on_click=edit_draft)
            if save.button('Create order', type='primary', use_container_width=True):
                try:
                    new_id = create_order(*draft['review'])
                except (ValueError, sqlite3.Error):
                    st.error('Could not save the order. Your draft is kept; please try again.')
                else:
                    draft['saved'] = new_id
                    st.session_state['dispatch_created'] = new_id
                    st.session_state['dispatch_selected'] = new_id
                    close_order_dialog()
                    st.rerun()
            return
        st.markdown('#### 1 / Order details')
        a, b = st.columns(2)
        draft['source'] = a.selectbox('Order source', SOURCES, index=SOURCES.index(draft['source']), key='dispatch_draft_source')
        draft['name'] = b.text_input('Recipient name', value=draft['name'], max_chars=80, placeholder='e.g. Alex Chen', key='dispatch_draft_name')
        draft['handoff'] = st.selectbox('Handoff to', RECIPIENTS, index=RECIPIENTS.index(draft['handoff']), key='dispatch_draft_handoff')
        st.markdown('#### 2 / Build the ticket')
        draft['foods'] = st.multiselect('Menu items', list(MENU), default=draft['foods'], placeholder='Add items…', key='dispatch_draft_foods')
        for food in draft['foods']:
            item = draft['items'].setdefault(food, {'quantity': 1, 'modifier': '', 'allergy': ''})
            label, quantity = st.columns([3, 1], vertical_alignment='center')
            label.text(food)
            item['quantity'] = quantity.number_input(f'{food} quantity', min_value=1, max_value=8,
                                                     value=item['quantity'], key=f'dispatch_draft_qty_{food}')
            with st.expander(f'{food} · modifications & allergy'):
                item['modifier'] = st.text_input(f'{food} modification', value=item['modifier'], max_chars=200,
                                                 key=f'dispatch_draft_mod_{food}')
                item['allergy'] = st.text_input(f'{food} allergy instruction', value=item['allergy'], max_chars=200,
                                                key=f'dispatch_draft_allergy_{food}')
        st.markdown('#### 3 / Pickup timing')
        draft['minutes'] = st.number_input('Pickup in minutes', min_value=5, max_value=90,
                                           value=draft['minutes'], step=5, key='dispatch_draft_minutes')
        if draft.get('error'):
            st.error(draft['error'])
        st.button('Review order', type='primary', use_container_width=True, on_click=review_draft)


@st.dialog('BREADY · Order', width='large')
def order_dialog(kind):
    if kind == 'new':
        render_creation()
    else:
        render_order_details()


@st.fragment(run_every='5s')
def render_summary():
    orders = fetch_orders()
    summary = summarize_orders(orders)
    counts = summary['statuses']
    due = sum(pickup_state(o)[1] in ('soon', 'overdue') for o in orders)
    st.markdown('<div class="dispatch-strip">' + ''.join(
        f'<span>{label}<b>{count}</b></span>' for label, count in [
            ('Active', summary['active']), ('In kitchen', counts['cooking']),
            ('Ready', counts['ready_to_pack'] + counts['packed']), ('Due soon / overdue', due)]
    ) + '</div>', unsafe_allow_html=True)


@st.fragment(run_every='5s')
def render_feed():
    orders = fetch_orders()
    visible = filter_orders(orders, st.session_state.get('dispatch_source') or 'All Sources',
                            st.session_state.get('dispatch_status', 'All'),
                            st.session_state.get('dispatch_search', ''),
                            st.session_state.get('dispatch_sort', 'Newest first'))
    st.markdown(f'<div class="dispatch-section-heading">Order queue <span>{len(visible)} of {len(orders)} · Select a row for details</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="dispatch-columns"><span>Order</span><span>Source</span><span>Recipient</span><span>Items</span><span>Status</span><span>Pickup</span></div>', unsafe_allow_html=True)
    with st.container(height=350, border=False, key='dispatch_queue'):
        if not visible:
            st.markdown('<div class="dispatch-empty"><h3>' + ('No orders yet' if not orders else 'No matching orders')
                        + '</h3><p>' + ('Use + New order to start a ticket.' if not orders else 'Change the channel or clear your filters.')
                        + '</p></div>', unsafe_allow_html=True)
        for order in visible:
            tone = pickup_state(order)[1]
            with st.container(key=f'ticket_{tone}_{order["id"]}'):
                if st.button(queue_row_label(order), key=f'view_{order["id"]}',
                             use_container_width=True, on_click=select_order, args=(order['id'],)):
                    st.rerun()


def render_intake():
    st.markdown('<style>' + Path(__file__).with_name('intake.css').read_text() + '</style>', unsafe_allow_html=True)
    with st.container(key='dispatch'):
        heading, action = st.columns([4, 1], vertical_alignment='center')
        heading.markdown('<div class="dispatch-identity">BREADY <span>/ DISPATCH</span></div>'
                         '<h2 class="dispatch-title">Incoming orders</h2>'
                         '<div class="dispatch-live"><i></i> Updates every 5s <span> / Simulated channels</span></div>', unsafe_allow_html=True)
        if action.button('+ New order', type='primary', use_container_width=True):
            if st.session_state.get('dispatch_draft', {}).get('saved'):
                st.session_state.pop('dispatch_draft')
                for key in list(st.session_state):
                    if key.startswith('dispatch_draft_'):
                        del st.session_state[key]
            st.session_state['dispatch_modal'] = 'new'
        if st.session_state.get('dispatch_created'):
            message, show = st.columns([4, 1], vertical_alignment='center')
            message.markdown(f'<div class="dispatch-saved">Order #{escape(str(st.session_state["dispatch_created"]))} created · Sent to kitchen</div>', unsafe_allow_html=True)
            show.button('Show created order', on_click=show_created, use_container_width=True)
        render_summary()
        with st.container(key='dispatch_filters'):
            st.session_state.setdefault('dispatch_source', 'All Sources')
            st.segmented_control('Channel', ['All Sources'] + SOURCES,
                                 key='dispatch_source', label_visibility='collapsed')
            search, status, sort, clear = st.columns([2.4, 1.3, 1.3, 1], vertical_alignment='bottom')
            search.text_input('Search orders', placeholder='Search order ID or recipient', key='dispatch_search')
            status.selectbox('Status', list(STATUS_GROUPS), key='dispatch_status')
            sort.selectbox('Sort', SORT_OPTIONS, key='dispatch_sort')
            clear.button('Clear filters', on_click=clear_filters, use_container_width=True)
        render_feed()

    if st.session_state.get('dispatch_modal'):
        # Consume the open request once. Native dismissal cannot reopen a stale
        # dialog on a later rerun; no newer Streamlit on_dismiss API is required.
        order_dialog(st.session_state.pop('dispatch_modal'))
