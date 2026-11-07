"""Feature 3 — realistic kitchen phrasing, end to end (rules parser only, no AI key, no Streamlit).
Run: python -m pytest tests/test_communication_phrases.py -q"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import database
from database import create_order, fetch_incidents, fetch_orders
from features.communication import impact, interpret as nlp, pipeline, store


def fresh(tmp_path):
    database.DB_PATH = str(tmp_path / 'phrases.db')
    database.init_db()
    store.reset_feature_data()
    with database.connect() as db:  # start from an empty restaurant: only the orders each test creates
        db.execute('DELETE FROM items')
        db.execute('DELETE FROM orders')
        db.execute('DELETE FROM incidents')


def same(x, y):  # ETAs are computed from the wall clock, so allow a few seconds of drift
    return abs((x - y).total_seconds()) < 5


def parse(text, orders=None):
    return nlp.interpret(text, orders=orders)['issues']


def shape(issues):
    return [(i['type'], i['confidence'], i['ingredient'] or i['item'] or i['station'] or i['order_id'], i['delay_minutes']) for i in issues]


@pytest.mark.parametrize('text', ["chicken's out", 'Chicken is gone', 'We ran out of chicken', "There's no more chicken",
                                  "We can't make chicken sandwiches anymore", 'Chicken sandwiches are off the menu'])
def test_shortage_phrasings_publish_automatically(text):
    assert shape(parse(text)) == [('ingredient_unavailable', 'high', 'chicken', 0)]


def test_personal_or_bare_statements_are_tentative_not_ignored():
    for text in ['I have no chicken', 'no chicken']:
        assert shape(parse(text)) == [('ingredient_unavailable', 'medium', 'chicken', 0)]


@pytest.mark.parametrize('text,expected', [
    ('The fryer is ten minutes behind', ('station_delay', 'high', 'Fryer', 10)),
    ('Fries are taking 10 more minutes', ('station_delay', 'high', 'Fryer', 10)),
    ('The fryer for the burger is going to take 10 more minutes', ('item_delay', 'high', 'Burger', 10)),
    ("The burger won't be off until 10 minutes from now", ('item_delay', 'high', 'Burger', 10)),
    ('The burgers are going to be about 10 minutes', ('item_delay', 'high', 'Burger', 10)),
    ('The pizza will be delayed by 10 minutes', ('item_delay', 'high', 'Pizza', 10)),
    ('The chicken is going to cause a 10 minute delay', ('item_delay', 'high', 'chicken', 10)),
    ('The grill is running slow', ('delay_unknown', 'medium', 'Grill', 0)),
    ('The burger order is going to be late', ('item_delay', 'medium', 'Burger', 0)),
])
def test_delay_phrasings(text, expected, tmp_path):
    fresh(tmp_path)  # item delays are only trusted when an open order still has that item to cook
    for item in ('Burger', 'Pizza', 'Chicken Sandwich', 'Salad', 'Fries'):
        create_order('Phone', 'Pickup customer', 30, [(item, 1, '', '')])
    assert shape(parse(text, fetch_orders())) == [expected]


@pytest.mark.parametrize('text', ["It's hot in here", 'Can someone get me a towel', 'Some funds', "I'm out of gloves", 'The fryer is hot',
                                  'we need to restock the napkins', 'ten minutes'])
def test_irrelevant_speech_is_ignored(text):
    assert parse(text) == []


def test_station_out_means_down_not_an_ingredient():
    assert shape(parse("the fryer's out")) == [('station_down', 'high', 'Fryer', 0)]


def test_spoken_order_number_matches_the_one_open_order_ending_in_it(tmp_path):
    fresh(tmp_path)
    oid = create_order('Phone', 'Pickup customer', 30, [('Burger', 1, '', '')])
    short = str(oid)[-2:]
    i = parse(f'Order {short} needs to be remade', fetch_orders())
    assert shape(i) == [('order_remake', 'high', str(oid), 0)] and 'matched' in i[0]['note']


def test_unknown_order_number_still_asks_instead_of_guessing(tmp_path):
    fresh(tmp_path)
    create_order('Phone', 'Pickup customer', 30, [('Burger', 1, '', '')])
    i = parse('Order 107 needs to be remade', fetch_orders())
    assert i[0]['confidence'] == 'low' and i[0]['question']


def test_end_to_end_only_impacted_orders_change(tmp_path):
    """Chicken out + fryer 10 min behind: chicken order BLOCKED, fries order delayed, grill/oven orders untouched."""
    fresh(tmp_path)
    chicken = create_order('DoorDash', 'Delivery driver', 40, [('Chicken Sandwich', 1, '', '')])
    fries = create_order('Website', 'Pickup customer', 14, [('Fries', 1, '', '')])
    burger = create_order('Phone', 'Pickup customer', 40, [('Burger', 1, '', '')])
    pizza = create_order('In-person POS', 'Dine-in server', 45, [('Pizza', 1, '', '')])

    def alerts():
        return {a['order']['id']: a for a in impact.build_alerts(fetch_orders(), fetch_incidents(), store.fetch_flags())}

    before = {k: alerts()[k]['revised_at'] for k in (chicken, fries, burger, pizza)}
    entry = pipeline.process_utterance("We're out of chicken and the fryer is ten minutes behind")
    assert entry['status'] == 'published' and entry['report_id']           # no confirmation click needed
    a = alerts()
    assert a[chicken]['timing']['category'] == 'blocked' and a[chicken]['revised_at'] is None
    assert 'substitution' in a[chicken]['headline'] and 'chicken' in a[chicken]['headline']
    assert a[fries]['severity'] in ('delayed', 'watch') and a[fries]['revised_at'] > before[fries]   # ETA revised
    assert 'fryer' in a[fries]['headline'].lower() and '10' in a[fries]['headline']
    for untouched in (burger, pizza):                                       # NOT updated blindly
        assert a[untouched]['severity'] == 'on_track' and same(a[untouched]['revised_at'], before[untouched])
    summary = impact.timing_summary(list(a.values()))
    assert summary['blocked'] == 1 and sum(summary.values()) == 4

    pipeline.process_utterance('The pizza will be delayed by 10 minutes')   # item-level delay moves only the pizza
    a2 = alerts()
    assert a2[pizza]['revised_at'] > before[pizza] and same(a2[burger]['revised_at'], before[burger])
    assert 'pizza' in a2[pizza]['headline'].lower()


def test_irrelevant_speech_changes_nothing(tmp_path):
    fresh(tmp_path)
    create_order('Phone', 'Pickup customer', 30, [('Burger', 1, '', '')])
    for text in ["It's hot in here", 'Can someone get me a towel', 'Some funds']:
        e = pipeline.process_utterance(text)
        assert e['status'] == 'ignored' and not e['report_id']
    assert not fetch_incidents() and not store.fetch_flags()
