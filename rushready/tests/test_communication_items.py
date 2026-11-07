"""Feature 3 tests: item-level delays, ETA recalculation, timing categories, server messages (no UI needed).
Run: python -m pytest tests/test_communication_items.py -q"""
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import database
from database import fetch_incidents, fetch_orders
from features.communication import impact, interpret as nlp, pipeline, store

NOW = datetime.now(timezone.utc)


def fresh(tmp_path):
    database.DB_PATH = str(tmp_path / 'items.db')
    database.init_db()
    store.reset_feature_data()


def say(text):
    return pipeline.process_utterance(text)


def parse(text):
    return nlp.interpret_rules(text)['issues']


def alerts_at(now=NOW):
    return {a['order']['id']: a for a in impact.build_alerts(fetch_orders(), fetch_incidents(), store.fetch_flags(), store.fetch_alert_rows(), now)}


def mins(a, b):
    return round((a - b).total_seconds() / 60, 1)


def test_item_and_ingredient_delay_phrases():
    d = parse('The fryer for the burger is going to take 10 more minutes')[0]
    assert (d['type'], d['item'], d['delay_minutes'], d['mode'], d['confidence']) == ('item_delay', 'Burger', 10, 'extra', 'high')
    assert 'Grill' in d['note']  # tells the chef the burger is cooked on the grill, not the fryer
    d = parse("The burger won't be off until 10 minutes from now")[0]
    assert (d['type'], d['item'], d['delay_minutes'], d['mode']) == ('item_delay', 'Burger', 10, 'ready_in')
    d = parse('The pizza will be delayed by 10 minutes')[0]
    assert (d['item'], d['delay_minutes'], d['confidence']) == ('Pizza', 10, 'high')
    d = parse('The chicken is going to cause a 10 minute delay')[0]
    assert (d['type'], d['item'], d['delay_minutes']) == ('item_delay', 'chicken', 10)
    d = parse('The burger order is going to be late')[0]
    assert (d['type'], d['item'], d['delay_minutes'], d['confidence']) == ('item_delay', 'Burger', 0, 'medium')  # no invented duration
    d = parse('Fries are taking 10 more minutes')[0]
    assert (d['type'], d['station'], d['delay_minutes']) == ('station_delay', 'Fryer', 10)
    assert parse('We messed up order 104')[0]['type'] == 'order_remake'
    for junk in ["It's hot in here", 'Can someone get me a towel', 'Some funds', 'uh the thing with the stuff']:
        assert parse(junk) == [], junk


def test_pizza_delay_revises_only_the_pizza_order(tmp_path):
    fresh(tmp_path)
    before = alerts_at()
    assert say('The pizza will be delayed by 10 minutes')['status'] == 'published'
    after = alerts_at()
    assert mins(after['1045']['revised_at'], before['1045']['order']['predicted_at']) == 10.0  # ETA recalculated
    assert after['1045']['promised_at'] == before['1045']['promised_at']                       # promise untouched
    assert {k for k, v in after.items() if v['severity'] != 'on_track'} == {'1045'}            # nobody else touched
    assert 'pizza' in after['1045']['headline'].lower() and '10 minutes' in after['1045']['headline']
    assert impact.eta_adjustments(fetch_orders(), fetch_incidents(), store.fetch_flags()) == {'1045': 10.0}


def test_fryer_for_the_burger_applies_to_burger_order_only(tmp_path):
    fresh(tmp_path)
    before = alerts_at()
    say('The fryer for the burger is going to take 10 more minutes')
    after = alerts_at()
    assert mins(after['1042']['revised_at'], before['1042']['order']['predicted_at']) == 10.0
    assert {k for k, v in after.items() if v['severity'] != 'on_track'} == {'1042'}


def test_ready_in_only_moves_the_eta_if_later_than_the_schedule(tmp_path):
    fresh(tmp_path)
    say("The burger won't be off until 10 minutes from now")  # schedule already says ~13 min: no change, and it says so
    a = alerts_at()['1042']
    assert a['extra_minutes'] == 0 and 'unchanged' in a['reasons'][0][0]
    say("The pizza won't be off until 40 minutes from now")   # far later than the ~22 min estimate: ETA moves
    b = alerts_at()['1045']
    assert b['extra_minutes'] > 10 and b['timing']['category'] in ('late', 'at_risk')


def test_station_delay_and_item_delay_are_not_double_counted(tmp_path):
    fresh(tmp_path)
    base = alerts_at()['1043']['order']['predicted_at']
    say('The fryer is ten minutes behind.')
    say('The chicken is going to cause a 10 minute delay')    # same 10 minutes seen from another angle
    a = alerts_at()['1043']
    assert mins(a['revised_at'], base) == 10.0                # +10, NOT +20
    assert a['extra_minutes'] == 0


def test_repeat_item_delay_replaces_never_adds_and_undo_restores(tmp_path):
    fresh(tmp_path)
    r1 = say('The pizza will be delayed by 10 minutes')
    assert say('The pizza will be delayed by ten minutes.')['status'] == 'repeat'
    r2 = say('The pizza will be delayed by 15 minutes')
    assert 'not added' in r2['lines'][0] and alerts_at()['1045']['extra_minutes'] == 15
    store.undo_report(r2['report_id'])
    assert alerts_at()['1045']['extra_minutes'] == 10
    store.undo_report(r1['report_id'])
    assert alerts_at()['1045']['severity'] == 'on_track'


def test_unknown_item_delay_is_possible_until_chef_gives_minutes(tmp_path):
    fresh(tmp_path)
    say('The burger order is going to be late')
    a = alerts_at()['1042']
    assert a['severity'] == 'possible' and a['revised_at'] is None
    flag = [f for f in store.fetch_flags() if f['active']][0]
    assert store.confirm_flag(flag['id'], 12)
    b = alerts_at()['1042']
    assert b['extra_minutes'] == 12 and b['severity'] in ('delayed', 'watch')


def test_timing_categories_and_summary(tmp_path):
    fresh(tmp_path)
    base = alerts_at()
    say("We're out of chicken and the fryer is ten minutes behind.")
    a = alerts_at()
    assert a['1043']['timing']['category'] == 'blocked'
    for oid in ('1044', '1045'):  # unaffected orders keep exactly the timing they had before the report
        assert a[oid]['severity'] == 'on_track' and a[oid]['timing'] == base[oid]['timing'], oid
    assert a['1044']['timing']['category'] == 'on_track'
    assert a['1045']['timing']['category'] == 'at_risk' and 'not affected' in a['1045']['headline']  # tight on its own, not by the report
    s = impact.timing_summary(list(a.values()))
    assert sum(s.values()) == len(a) == 4
    assert (s['on_track'], s['at_risk'], s['late'], s['blocked']) == (1, 1, 1, 1)  # #1044 / #1045 / #1042 / #1043
    assert a['1042']['timing']['category'] in ('at_risk', 'late')  # fries sit on the delayed fryer


def test_server_messages_are_generated_from_data(tmp_path):
    fresh(tmp_path)
    say("We're out of chicken and the fryer is ten minutes behind.")
    a = alerts_at()
    assert 'substitution' in a['1043']['headline'] and 'chicken is unavailable' in a['1043']['headline']
    assert 'fryer is 10 minutes behind' in a['1042']['headline']
    assert a['1044']['headline'] == 'Order #1044 is on track.'
    say('The fryer is fifteen minutes behind.')                 # new data -> new message (not static text)
    assert '15 minutes behind' in alerts_at()['1042']['headline']
    h = impact._headline('107', 'watch', {'category': 'on_track', 'slack': 8.0, 'late_minutes': 0},
                         [('the fryer is 10 minutes behind', 'confirmed', 'delay')])
    assert h == 'Order #107 remains on track even though the fryer is 10 minutes behind (8.0 min of slack).'
