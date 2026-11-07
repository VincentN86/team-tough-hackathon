"""MAIN-APP UI — focused packing view for ONE order (opens inside the Front Desk left pane, not on a new page).

OWNERSHIP: presentation only. Packing LOGIC is Feature 4's and is unchanged: every action calls the same database functions the
original `screen_packer` in app.py uses (verify_item_packed, verify_special, seal_order, handoff_order) with the same widget keys
(packed_<item>, mod_<order>, allergy_<order>, seal_<order>) and the same rules (items must be 'ready' before they can be ticked, sealing
needs the modification / allergy confirmations). The original screen is still available under Front Desk -> Classic.
PROPOSAL for the Feature 4 owner: adopt this view as the default packer UI, or tell us what to change.

Edit here to change: item rows, allergy / modification emphasis, the order header, button labels.
"""
import html

import streamlit as st

from database import handoff_order, seal_order, verify_item_packed, verify_special
from ui.theme import clock, inject_css, pill

CSS = '''<style>
.pk-head{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;margin-bottom:1rem}   /* 1rem: offsets Streamlit's -1rem markdown margin */
.pk-id{font-size:1.4rem;font-weight:800}
.pk-sub{color:var(--rr-muted,#66645f);font-size:.9rem}
.pk-alert{border-left:4px solid var(--rr-late,#b42318);background:var(--rr-late-bg,#fee4e2);padding:8px 12px;border-radius:0 8px 8px 0;font-weight:600;margin-bottom:1rem}
.pk-item{padding:4px 0;margin-bottom:1rem}
.pk-name{font-weight:700;font-size:1.05rem}
.pk-mod{margin-top:2px;font-weight:600}                                 /* modification: always visible */
.pk-allergy{margin-top:2px;font-weight:800;color:var(--rr-late,#b42318)} /* allergy: always visible, strongest emphasis */
.pk-state{font-size:.8rem;color:var(--rr-muted,#66645f)}
</style>'''


def render_packing_detail(order, alert, on_back):
    """order: a dict from database.fetch_orders(); alert: Feature 3's alert for this order (or None); on_back(): return to the list."""
    inject_css(CSS)
    oid = order['id']
    if st.button('Back to orders', key='pk_back'):
        on_back()
    est = f" · Est {clock(alert['revised_at'])}" if alert and alert['revised_at'] else ''
    st.markdown(f"<div class='pk-head'><span class='pk-id'>#{html.escape(str(oid))}</span><span>{html.escape(order['source'])} · "
                f"{html.escape(order['recipient'])}</span><span class='pk-sub'>Due {clock(order['pickup_at'])}{est}</span></div>", unsafe_allow_html=True)
    if alert and alert['severity'] != 'on_track':
        st.markdown(f"<div class='pk-alert'>{html.escape(alert['headline'])}</div>", unsafe_allow_html=True)

    packed = order['status'] == 'packed'
    for it in order['items']:
        a, b = st.columns([5, 2], vertical_alignment='center')
        with a:
            extra = ''
            if it['modifier']:
                extra += f"<div class='pk-mod'>Modification: {html.escape(it['modifier'])}</div>"
            if it['allergy']:
                extra += f"<div class='pk-allergy'>ALLERGY: {html.escape(it['allergy'])}</div>"
            st.markdown(f"<div class='pk-item'><span class='pk-name'>{it['quantity']}× {html.escape(it['name'])}</span> "
                        f"<span class='pk-state'>{html.escape(it['status'].replace('_', ' '))}</span>{extra}</div>", unsafe_allow_html=True)
        with b:
            checked = st.checkbox('Packed', key=f"packed_{it['id']}", value=bool(it['pack_verified']), disabled=it['status'] != 'ready' or packed)
            if it['status'] == 'ready' and not packed and checked != bool(it['pack_verified']):
                verify_item_packed(it['id'], checked)
                st.rerun()

    if not packed:
        if any(i['modifier'].strip() for i in order['items']):
            val = st.checkbox('I confirmed the requested modifications', value=bool(order['modifications_verified']), key=f'mod_{oid}')
            if val != bool(order['modifications_verified']):
                verify_special(oid, 'modifications_verified', val)
                st.rerun()
        if any(i['allergy'].strip() for i in order['items']):
            val = st.checkbox('I checked the allergy instructions with kitchen staff', value=bool(order['allergies_verified']), key=f'allergy_{oid}')
            if val != bool(order['allergies_verified']):
                verify_special(oid, 'allergies_verified', val)
                st.rerun()
        waiting = sum(i['status'] != 'ready' for i in order['items'])
        if waiting:
            st.markdown(pill(f'Waiting on kitchen: {waiting} item(s)', 'risk'), unsafe_allow_html=True)
        if st.button('Mark Packed & Sealed', key=f'seal_{oid}', type='primary', use_container_width=True):
            ok, message = seal_order(oid)
            if ok:
                st.toast(f'#{oid}: {message}')
                on_back()
            else:
                st.warning(message)
        st.caption(f"Bag label: ORDER {oid} · {order['recipient'].upper()} · {order['source']}")
    else:
        st.markdown(pill('Packed and sealed', 'ok'), unsafe_allow_html=True)
        if st.button('Hand Off', key=f'pk_handoff_{oid}', type='primary', use_container_width=True):
            if handoff_order(oid):
                st.toast(f'#{oid} handed off')
                on_back()
