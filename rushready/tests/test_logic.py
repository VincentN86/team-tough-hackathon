import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import database
from ai_agent import demo_extract
from scheduler import schedule


def fresh_demo(tmp_path):
    database.DB_PATH = str(tmp_path/'test_kitchen.db')
    database.init_db()
    return database.fetch_orders()


def test_demo_seed_and_source(tmp_path):
    orders=fresh_demo(tmp_path)
    assert len(orders)==4
    assert {x['source'] for x in orders}=={'DoorDash','Uber Eats','In-person POS','Website'}


def test_chef_report_affects_orders(tmp_path):
    orders=fresh_demo(tmp_path)
    note='We are out of chicken. The fryer is running 10 minutes behind.'
    fields=demo_extract(note)
    assert fields['ingredient']=='chicken'
    assert fields['station']=='Fryer'
    assert fields['delay_minutes']==10
    database.add_incident(note,fields['ingredient'],fields['station'],fields['delay_minutes'])
    r={x['id']:x for x in schedule(database.fetch_orders(),database.fetch_incidents())}
    assert r['1043']['blocked'] is True
    assert r['1042']['matching_incidents']
    assert r['1045']['blocked'] is False
    active=database.fetch_incidents()[0]
    database.resolve_incident(active['id'])
    r2={x['id']:x for x in schedule(database.fetch_orders(),database.fetch_incidents())}
    assert r2['1043']['blocked'] is False


def test_packing_requires_modification_and_allergy_confirmation(tmp_path):
    orders=fresh_demo(tmp_path)
    order=next(o for o in orders if o['id']=='1044')
    for it in order['items']:
        database.update_item(it['id'],'ready')
        database.verify_item_packed(it['id'],True)
    ok,msg=database.seal_order('1044')
    assert not ok and 'modifications' in msg
    database.verify_special('1044','modifications_verified',True)
    ok,msg=database.seal_order('1044')
    assert not ok and 'allergy' in msg
    database.verify_special('1044','allergies_verified',True)
    ok,msg=database.seal_order('1044')
    assert ok
    assert database.handoff_order('1044')


def test_long_pizza_can_beat_short_salad(tmp_path):
    fresh_demo(tmp_path)
    now=datetime.now(timezone.utc)
    orders=[
      dict(id='1',source='POS',recipient='Pickup',received_at=(now-timedelta(minutes=5)).isoformat(),
           pickup_at=(now+timedelta(minutes=18)).isoformat(),status='queued',
           items=[dict(name='Salad',station='Cold',quantity=1,prep_minutes=4,status='queued',ingredients='',modifier='',allergy='')]),
      dict(id='2',source='Web',recipient='Pickup',received_at=(now-timedelta(minutes=1)).isoformat(),
           pickup_at=(now+timedelta(minutes=18)).isoformat(),status='queued',
           items=[dict(name='Pizza',station='Oven',quantity=1,prep_minutes=20,status='queued',ingredients='',modifier='',allergy='')])
    ]
    ranked=schedule(orders,[],now)
    assert ranked[0]['id']=='2'
