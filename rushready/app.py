"""RushReady NOVA 2026 — Front House demo.
Run with: python3 -m streamlit run app.py
"""
from datetime import datetime, timezone
import os

import streamlit as st
from database import (MENU,SOURCES,RECIPIENTS,STATIONS,init_db,reset_demo,create_order,
                      fetch_orders,fetch_incidents,update_item,verify_item_packed,
                      verify_special,seal_order,handoff_order,add_incident,resolve_incident)
from scheduler import schedule,batch_hints
from ai_agent import parse_issue,transcribe_wav,inspect_packing_photo

st.set_page_config(page_title='RushReady • NOVA 2026',page_icon='🍔',layout='wide')
init_db()

st.markdown('''<style>
.block-container {max-width: 1360px; padding-top: 1.6rem;}
[data-testid="stMetric"]{border:1px solid #dae1e5; border-radius:12px; padding:12px;}
</style>''',unsafe_allow_html=True)

try:
    configured=st.secrets.get('OPENROUTER_API_KEY','')
    default_model=st.secrets.get('OPENROUTER_MODEL','openrouter/auto')
except (FileNotFoundError,KeyError):
    configured=''
    default_model='openrouter/auto'

with st.sidebar:
    st.title('⚙️ RushReady')
    st.caption('NOVA hackathon • Fictional order data')
    KEY=os.environ.get('OPENROUTER_API_KEY','') or configured
    if KEY:
        st.success('OpenRouter key configured')
    else:
        KEY=st.text_input('OpenRouter API key (optional)',type='password')
    MODEL=st.text_input('OpenRouter text model', value=default_model)
    STT_MODEL=st.text_input('Speech-to-text model', value='openai/whisper-1')
    VISION_MODEL=st.text_input('Vision model',value=default_model)
    st.caption('Model access depends on sponsor credits; AI calls cost credits. Never commit your API key.')
    st.divider()
    if st.button('Reset demo restaurant',use_container_width=True):
        reset_demo()
        for k in ['issue_preview','chef_report_text','photo_result']:
            st.session_state.pop(k,None)
        st.rerun()
    if st.button('Refresh', use_container_width=True):
        st.rerun()

st.title('🍔 RushReady')
st.caption('One order feed. Smarter kitchen priorities. Safer handoffs.  •  DEMO ONLY — no live DoorDash/Uber Eats integrations or customer notifications.')


def clock(t):
    return datetime.fromisoformat(t).astimezone().strftime('%I:%M %p').lstrip('0')


def urgency_chip(row):
    val=row['urgency']
    if val=='BLOCKED': st.error('🛑 Ingredient unavailable')
    elif val=='LATE': st.error(f"⚠️ Predicted {row['late_minutes']} min late")
    elif val=='RISK': st.warning(f"⚠️ At risk • {row['slack']} min slack")
    else: st.success(f"✓ On track • {row['slack']} min slack")


def order_header(o):
    st.markdown(f"**#{o['id']}** — {o['source']} · {o['recipient']}")
    st.caption(f"Arrived {clock(o['received_at'])} · Promised {clock(o['pickup_at'])} · Status: {o['status'].replace('_',' ')}")


def item_text(item):
    return f"{item['quantity']}× {item['name']}"


def incident_summary(o):
    result=[]
    for issue in o['matching_incidents']:
        parts=[]
        if issue['ingredient']:
            parts.append('Unavailable: '+issue['ingredient'])
        if issue['station']:
            parts.append(f"{issue['station']} delayed {issue['delay_minutes']} min")
        desc=', '.join(parts)
        if desc not in result:
            result.append(desc)
    return '; '.join(result)


tabs=st.tabs(['📥 Order Intake','👨‍🍳 Cook & AI Agent','📦 Packer','🛎️ Front Desk','📊 Workflow'])

with tabs[0]:
    left,right=st.columns([1,1.6],gap='large')
    with left:
        st.subheader('Simulate a new order')
        st.caption('Choose a platform to simulate a unified feed. No platform API is connected.')
        with st.form('new_order',clear_on_submit=False):
            source=st.selectbox('Source',SOURCES)
            recipient=st.selectbox('Handoff to',RECIPIENTS)
            minutes=st.slider('Pickup deadline: minutes from now',5,90,25,1)
            chosen=st.multiselect('Food items',list(MENU),default=['Burger','Fries'])
            qty=st.number_input('Quantity of EACH selected item',1,8,1)
            modifier=st.text_input('Modifier for first item (optional)',placeholder='No onions')
            allergy=st.text_input('Allergy instruction for first item (optional)',placeholder='Employee must verify')
            submitted=st.form_submit_button('Add incoming order',type='primary',use_container_width=True)
        if submitted:
            if not chosen:
                st.warning('Choose at least one menu item.')
            else:
                lines=[(name,qty, modifier if idx==0 else '',allergy if idx==0 else '') for idx,name in enumerate(chosen)]
                new_id=create_order(source,recipient,minutes,lines)
                st.success(f'Order #{new_id} added to the shared database.')
                st.rerun()
    with right:
        st.subheader('All platforms → one feed')
        @st.fragment(run_every='5s')
        def intake_feed():
            orders=fetch_orders()
            for o in sorted(orders,key=lambda x:x['received_at'],reverse=True):
                with st.container(border=True):
                    order_header(o)
                    st.write(' · '.join(item_text(i) for i in o['items']))
                    if any(i['modifier'] for i in o['items']):
                        st.info('Modifiers: '+'; '.join(f"{i['name']}: {i['modifier']}" for i in o['items'] if i['modifier']))
                    if any(i['allergy'] for i in o['items']):
                        st.warning('ALLERGY INSTRUCTIONS: Staff must verify')
        intake_feed()

with tabs[1]:
    st.subheader('Kitchen tickets — ranked by deadline risk')
    st.caption('Priority uses estimated latest-start times, not simple arrival order. Each station processes one ticket line at a time in this demo.')
    station_filter=st.selectbox('Cooking station', ['All stations']+STATIONS)
    @st.fragment(run_every='5s')
    def cook_queue():
        ranked=schedule(fetch_orders(),fetch_incidents())
        stt=st.columns(3)
        stt[0].metric('Open orders',len(ranked))
        stt[1].metric('At risk / late',sum(x['urgency'] in ('RISK','LATE') for x in ranked))
        stt[2].metric('Blocked',sum(x['blocked'] for x in ranked))
        for station,name,count in batch_hints(fetch_orders()):
            if station_filter=='All stations' or station_filter==station:
                st.info(f'💡 Batching hint: **{count}× {name}** needed at {station}')
        for priority,o in enumerate(ranked,start=1):
            visible=[i for i in o['items'] if station_filter=='All stations' or i['station']==station_filter]
            if not visible: continue
            with st.container(border=True):
                a,b=st.columns([2.5,1])
                with a:
                    st.markdown(f"### Priority {priority} · Order #{o['id']}")
                    st.caption(f"{o['source']} · Received {clock(o['received_at'])} · Pickup {clock(o['pickup_at'])}")
                    st.write('**Predicted ready:** '+('Blocked until resolved' if o['predicted_at'] is None else o['predicted_at'].astimezone().strftime('%I:%M %p').lstrip('0')))
                with b:
                    urgency_chip(o)
                if o['matching_incidents']:
                    st.warning('Kitchen alert: '+incident_summary(o))
                for it in visible:
                    x,y,z=st.columns([4,1.3,1.3],vertical_alignment='center')
                    with x:
                        st.markdown(f"**{item_text(it)}** — {it['station']} · {it['prep_minutes']} min/base · **{it['status']}**")
                        if it['modifier']:
                            st.info('MODIFICATION: '+it['modifier'])
                        if it['allergy']:
                            st.error('ALLERGY: '+it['allergy'])
                    with y:
                        if st.button('Start',key=f"start_{it['id']}",disabled=it['status']!='queued',use_container_width=True):
                            update_item(it['id'],'cooking');st.rerun()
                    with z:
                        if st.button('✓ Ready',key=f"ready_{it['id']}",disabled=it['status']=='ready',use_container_width=True):
                            update_item(it['id'],'ready');st.rerun()
    cook_queue()
    st.divider()
    st.subheader('🤖 Chef → Server communication agent')
    st.write('Report an unavailable ingredient or a kitchen station delay. Review AI interpretation before applying it.')
    if 'chef_report_text' not in st.session_state:
        st.session_state.chef_report_text='We are out of chicken. The fryer is running 10 minutes behind.'
    recorded=st.audio_input('Optional: record a chef report')
    if st.button('Transcribe recording (OpenRouter)', disabled=recorded is None):
        if not KEY: st.warning('Add an OpenRouter API key first.')
        else:
            try:
                with st.spinner('Transcribing...'):
                    st.session_state.chef_report_text=transcribe_wav(recorded.getvalue(),KEY,STT_MODEL)
                st.rerun()
            except Exception as e:
                st.error(f'Transcription unavailable: {e}')
    with st.form('chef_report'):
        report=st.text_area('Chef report (type or transcribe)',key='chef_report_text',height=100)
        analyze=st.form_submit_button('Analyze report',type='primary')
    if analyze:
        if not report.strip(): st.warning('Enter a chef report.')
        else:
            try:
                with st.spinner('Interpreting report...'):
                    result,source=parse_issue(report.strip(),KEY,MODEL)
                st.session_state.issue_preview={'report':report.strip(),'result':result,'via':source}
            except Exception as e:
                st.error(f'AI analysis failed: {e}. You can remove the key to try the demo parser.')
    preview=st.session_state.get('issue_preview')
    if preview:
        st.write('**Review before applying:**',preview['via'])
        st.json(preview['result'])
        fields=preview['result']
        if not fields['ingredient'] and not fields['delay_minutes']:
            st.warning('No actionable inventory outage or station delay detected. Rephrase the report.')
        elif st.button('Confirm and notify Front Desk',type='primary'):
            add_incident(preview['report'],fields['ingredient'],fields['station'],fields['delay_minutes'])
            st.session_state.pop('issue_preview',None)
            st.success('Incident saved. Orders have been rescored, and Front Desk alerts are available.')
            st.rerun()
    st.divider()
    st.subheader('Active incidents')
    @st.fragment(run_every='5s')
    def active_incidents():
        incidents=[x for x in fetch_incidents() if x['active']]
        if not incidents: st.caption('No active kitchen issues.')
        for i in incidents:
            a,b=st.columns([5,1])
            a.write(f"**#{i['id']}** {i['raw_note']}")
            if b.button('Resolve',key=f"resolve_{i['id']}",use_container_width=True):
                resolve_incident(i['id']);st.rerun()
    active_incidents()

with tabs[2]:
    st.subheader('Packing verification')
    st.caption('A human packer checks each item. Photos do not verify sealed containers, hidden modifiers, or allergens.')
    @st.fragment(run_every='5s')
    def packer():
        orders=[o for o in fetch_orders() if o['status'] not in ('handed_off','packed')]
        for order in orders:
            with st.container(border=True):
                order_header(order)
                pending=sum(it['status']!='ready' for it in order['items'])
                if pending: st.warning(f'⏳ {pending} item line(s) still waiting for the kitchen')
                else: st.success('All cooked items have arrived at packing')
                for it in order['items']:
                    cols=st.columns([3,1.1],vertical_alignment='center')
                    with cols[0]:
                        st.write(f"**{item_text(it)}** — {it['status'].replace('_',' ')}")
                        if it['modifier']: st.info('MODIFICATION: '+it['modifier'])
                        if it['allergy']: st.error('ALLERGY: '+it['allergy'])
                    with cols[1]:
                        checked=st.checkbox('Packed',key=f"packed_{it['id']}",value=bool(it['pack_verified']),
                                            disabled=it['status']!='ready')
                        if it['status']=='ready' and checked != bool(it['pack_verified']):
                            verify_item_packed(it['id'],checked);st.rerun()
                if any(i['modifier'].strip() for i in order['items']):
                    val=st.checkbox('I manually confirmed the requested modifications',
                        value=bool(order['modifications_verified']),key=f"mod_{order['id']}")
                    if val != bool(order['modifications_verified']):
                        verify_special(order['id'],'modifications_verified',val);st.rerun()
                if any(i['allergy'].strip() for i in order['items']):
                    val=st.checkbox('I independently checked the allergy instructions with kitchen staff',
                        value=bool(order['allergies_verified']),key=f"allergy_{order['id']}")
                    if val != bool(order['allergies_verified']):
                        verify_special(order['id'],'allergies_verified',val);st.rerun()
                st.caption(f"🏷️ Bag label: ORDER {order['id']} · {order['recipient'].upper()} · {order['source']}")
                if st.button('✅ Staff confirms bag packed / sealed',key=f"seal_{order['id']}",type='primary'):
                    ok,message=seal_order(order['id'])
                    if ok: st.success(message);st.rerun()
                    else: st.warning(message)
    packer()
    st.divider()
    with st.expander('📷 Optional AI photo review — assistive only'):
        st.caption('Use a model that supports image input. Use sample food photos, not customer information.')
        camera=st.camera_input('Take a packing photo')
        expected=st.text_input('Expected visible items',value='Burger, fries, drink')
        if st.button('Check visible items with AI',disabled=camera is None):
            if not KEY: st.warning('OpenRouter key required.')
            else:
                try:
                    with st.spinner('Reviewing image...'):
                        st.session_state.photo_result=inspect_packing_photo(camera.getvalue(),camera.type,expected,KEY,VISION_MODEL)
                except Exception as e: st.error(f'Vision request failed: {e}')
        if st.session_state.get('photo_result'):
            st.info(st.session_state.photo_result)
            st.caption('Photo analysis is only a suggestion. Employee sign-off is always required.')

with tabs[3]:
    st.subheader('Server / front desk — pickup coordination')
    @st.fragment(run_every='5s')
    def front_desk():
        records=schedule(fetch_orders(),fetch_incidents())
        for o in records:
            with st.container(border=True):
                order_header(o)
                urgency_chip(o)
                if o['matching_incidents']:
                    st.warning('Chef report impacts this order: '+incident_summary(o))
                    if o['blocked']:
                        msg=f"Order #{o['id']} ({o['source']}) cannot be completed as ordered: an ingredient is unavailable. Ask the customer about approved alternatives before promising a new pickup time."
                    else:
                        finish=o['predicted_at'].astimezone().strftime('%I:%M %p').lstrip('0')
                        msg=f"Order #{o['id']} ({o['source']}) may be delayed because of kitchen congestion. Current estimated ready time is {finish}. Please check with the kitchen before notifying the customer."
                    st.text_area('Suggested message — not sent',msg,height=95,key=f"draft_{o['id']}")
                elif o['status']=='ready_to_pack':
                    st.info('Cooking complete; waiting for packer confirmation.')
                elif o['status']=='queued':
                    st.caption('Order waiting to begin preparation.')
        packed=[o for o in fetch_orders() if o['status']=='packed']
        st.subheader('✅ Packed — ready for handoff')
        if not packed: st.caption('No orders packed yet.')
        for o in packed:
            a,b=st.columns([4,1.4],vertical_alignment='center')
            a.write(f"**#{o['id']}** — {o['source']} · **{o['recipient']}** · Bag label #{o['id']}")
            if b.button('Confirm handed off',key=f"handoff_{o['id']}",type='primary'):
                if handoff_order(o['id']): st.rerun()
        completed=[o for o in fetch_orders() if o['status']=='handed_off']
        if completed: st.success(f"{len(completed)} order(s) handed off in this demo.")
        st.caption('No SMS, push notification, DoorDash, or Uber Eats message is actually sent. This screen prepares staff-facing drafts.')
    front_desk()

with tabs[4]:
    st.subheader('System implementation notes')
    st.markdown('''
    **Order lifecycle:** Incoming → Cooking → Ready to pack → Staff verified/packed → Handed off.

    **What is automated:** Deadline-based station sequencing, estimated finish times,
    ingredient-outage and station-delay detection, affected-order flags, batch hints,
    and draft front-desk messages.

    **What requires employees:** Confirm chef report, start/finish cooking, manually verify
    modifiers and allergen instructions, confirm packing and sealing, then confirm handoff.

    **Honest limitations:** The prep-time estimates use a simple scheduling heuristic;
    they are not learned from historical orders. This demo simulates marketplace order
    sources, and does not send real customer notifications. SQLite is shared by users
    on one running instance but does not guarantee persistence on hosted servers.
    ''')
    st.code('python3 -m pip install -r requirements.txt\npython3 -m streamlit run app.py',language='bash')
