"""Feature 3 UNIT tests — no Streamlit UI needed. Run: python -m pytest tests/test_communication.py -q"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import database
from database import fetch_incidents, fetch_orders
from features.communication import impact, interpret as nlp, pipeline, store


def fresh(tmp_path):
    database.DB_PATH = str(tmp_path / 'comm.db')
    database.init_db()
    store.reset_feature_data()


def say(text, **kw):
    return pipeline.process_utterance(text, **kw)


def alerts():
    return {a['order']['id']: a for a in impact.build_alerts(fetch_orders(), fetch_incidents(), store.fetch_flags(), store.fetch_alert_rows())}


def parse(text):
    return nlp.interpret_rules(text)['issues']


def active_inc():
    return [i for i in fetch_incidents() if i['active']]


# ---------------------------------------------------------------- interpretation
@pytest.mark.parametrize('text', ["We're out of chicken.", "We don't have any chicken left.", "There's no more chicken.",
                                  'We ran out of chicken.', "We're all out of chicken.", 'No chicken left.'])
def test_clear_shortage_variants_are_high_confidence(text):
    i = parse(text)
    assert [(x['type'], x['ingredient'], x['confidence']) for x in i] == [('ingredient_unavailable', 'chicken', 'high')]


def test_ambiguous_phrasings_are_medium_not_ignored():
    for text in ['I have no chicken.', "We can't make the chicken sandwiches anymore."]:
        i = parse(text)
        assert i and i[0]['type'] == 'ingredient_unavailable' and i[0]['ingredient'] == 'chicken' and i[0]['confidence'] == 'medium', text


def test_prep_status_is_not_a_shortage():
    for text in ['We have no cooked chicken ready.', 'I have no chicken ready.']:
        i = parse(text)
        assert [(x['type'], x['confidence']) for x in i] == [('prep_wait', 'medium')], text


def test_order_specific_complaint_is_not_a_restaurant_shortage():
    i = parse('There is no chicken on order 1043.')
    assert [(x['type'], x['order_id']) for x in i] == [('order_issue', '1043')]


def test_natural_delay_phrasings():
    d = parse("The fryer's ten minutes behind.")[0]
    assert (d['type'], d['station'], d['delay_minutes']) == ('station_delay', 'Fryer', 10)
    d = parse('Everything from the fryer needs another fifteen minutes.')[0]
    assert (d['type'], d['delay_minutes']) == ('station_delay', 15)
    for text in ['Fries are taking forever.', 'Fryer is running slow.', "We're backed up on fried food.", 'The grill is behind schedule.']:
        d = parse(text)[0]
        assert d['type'] == 'delay_unknown' and d['delay_minutes'] == 0 and d['confidence'] == 'medium', text


def test_three_issues_in_one_report():
    i = parse("We don't have any chicken, the fryer is ten minutes behind, and order 107 needs to be remade.")
    assert [x['type'] for x in i] == ['ingredient_unavailable', 'station_delay', 'order_remake']
    assert i[2]['order_id'] == '107'


def test_irrelevant_speech_ignored():
    for text in ["It's a really nice day.", "It's hot in here. Someone turn on the fan.", 'Can someone bring me another cutting board?', '   ']:
        assert parse(text) == [], text


def test_low_confidence_when_unspecific_or_unknown_order(tmp_path):
    fresh(tmp_path)
    assert parse("We're running behind.")[0]['confidence'] == 'low'
    assert say("We're running behind.")['status'] == 'clarify'
    e = say('Order 999 needs to be remade.')
    assert e['status'] == 'clarify' and not store.fetch_flags()  # never invent an order


def test_llm_output_is_validated():
    bad = [{'type': 'station_delay', 'station': 'Fryer', 'delay_minutes': 999, 'confidence': 'high'},
           {'type': 'nonsense'}, {'type': 'ingredient_unavailable', 'ingredient': '<script>'},
           {'type': 'ingredient_low', 'ingredient': 'lettuce', 'confidence': 'high'}]
    out = nlp.validate_issues(bad)
    assert [(x['type'], x['confidence']) for x in out] == [('delay_unknown', 'medium'), ('ingredient_low', 'medium')]


def test_llm_called_only_when_useful(monkeypatch):
    calls = []
    monkeypatch.setattr(nlp, 'interpret_llm', lambda *a, **k: calls.append(1) or {'issues': [], 'ignored': [], 'via': 'x'})
    nlp.interpret("It's a really nice day.", key='k')          # chit-chat: no AI call
    nlp.interpret("We're out of chicken.", key='k')            # clear high-confidence: rules are enough
    assert calls == []
    nlp.interpret('I have no chicken.', key='k')               # ambiguous: ask the AI
    assert calls == [1]


def test_llm_failure_falls_back_to_rules(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError('network down')
    monkeypatch.setattr(nlp, 'interpret_llm', boom)
    res = nlp.interpret('I have no chicken.', key='k')
    assert res['issues'] and 'AI unavailable' in res['via']


# ------------------------------------------------------------- publishing / impact
def test_simple_shortage_flags_matching_orders_only(tmp_path):
    fresh(tmp_path)
    e = say("We're out of chicken.")
    assert e['status'] == 'published'
    a = alerts()
    assert a['1043']['severity'] == 'urgent' and a['1043']['revised_at'] is None
    assert {k for k, v in a.items() if v['severity'] != 'on_track'} == {'1043'}


def test_ambiguous_statement_is_provisional_and_changes_nothing_else(tmp_path):
    fresh(tmp_path)
    before = [(o['id'], o['pickup_at'], o['status']) for o in fetch_orders()]
    e = say('I have no chicken.')
    assert e['status'] == 'provisional' and active_inc() == []        # no real incident, nothing blocked
    a = alerts()['1043']
    assert a['severity'] == 'possible' and a['revised_at'] is None
    assert 'do NOT cancel' in ' '.join(a['actions'])
    assert before == [(o['id'], o['pickup_at'], o['status']) for o in fetch_orders()]


def test_prep_wait_advisory_is_distinct_from_shortage(tmp_path):
    fresh(tmp_path)
    say('We have no cooked chicken ready.')
    a = alerts()['1043']
    assert a['severity'] == 'possible' and 'preparation delay' in a['reasons'][0][0] and active_inc() == []


def test_order_specific_issue_touches_only_that_order(tmp_path):
    fresh(tmp_path)
    say('There is no chicken on order 1043.')
    assert {k for k, v in alerts().items() if v['severity'] != 'on_track'} == {'1043'}


def test_combined_report_matches_only_relevant_orders(tmp_path):
    fresh(tmp_path)
    say("No chicken left. Fryer's ten minutes behind.")
    a = alerts()
    assert a['1043']['severity'] == 'urgent'
    assert a['1042']['severity'] in ('delayed', 'watch')               # has Fries on the fryer
    assert a['1044']['severity'] == 'on_track' and a['1045']['severity'] == 'on_track'


def test_repeat_does_not_double_count_and_new_number_replaces(tmp_path):
    fresh(tmp_path)
    assert say('The fryer is ten minutes behind.')['status'] == 'published'
    assert say('The fryer is running 10 minutes behind.')['status'] == 'repeat'   # duplicate outcome
    assert [i['delay_minutes'] for i in active_inc()] == [10]
    assert say('The fryer is fifteen minutes behind.')['lines'][0].endswith('not added)')
    assert [i['delay_minutes'] for i in active_inc()] == [15]


def test_speech_engine_repeat_window():
    recent = {}
    assert pipeline.process_utterance('The weather is nice', recent=recent, now=100)['status'] == 'ignored'
    assert pipeline.process_utterance('the weather is nice!', recent=recent, now=105)['status'] == 'repeat'
    assert pipeline.process_utterance('The weather is nice', recent=recent, now=200)['status'] == 'ignored'


def test_unknown_delay_never_invents_an_eta(tmp_path):
    fresh(tmp_path)
    say('Fries are taking forever.')
    a = alerts()
    assert active_inc() == [] and a['1042']['severity'] == 'possible' and a['1042']['revised_at'] is None


def test_recovery_phrase_resolves_and_undo_restores(tmp_path):
    fresh(tmp_path)
    r1 = say('The fryer is ten minutes behind.')
    assert active_inc()
    r2 = say('The fryer is back to normal.')
    assert r2['status'] == 'published' and active_inc() == []
    again = say('The fryer is back to normal.')                           # nothing left to resolve -> no change, no report
    assert again['status'] == 'repeat' and again['report_id'] is None
    store.undo_report(r2['report_id'])
    assert [i['delay_minutes'] for i in active_inc()] == [10]
    assert store.undo_report(r2['report_id']) is False                  # safe to press twice
    store.undo_report(r1['report_id'])
    assert active_inc() == []


def test_provisional_can_be_confirmed_or_dismissed(tmp_path):
    fresh(tmp_path)
    say('I have no chicken.')
    flag = [f for f in store.fetch_flags() if f['active']][0]
    assert store.confirm_flag(flag['id'])
    assert alerts()['1043']['severity'] == 'urgent' and [i['ingredient'] for i in active_inc()] == ['chicken']
    say('Fryer is running slow.')
    f2 = [f for f in store.fetch_flags() if f['active']][0]
    store.dismiss_flag(f2['id'])
    assert alerts()['1042']['severity'] == 'on_track'


def test_station_down_and_remake_have_no_eta(tmp_path):
    fresh(tmp_path)
    say('The grill is broken.')
    say('Order 1044 needs to be remade.')
    a = alerts()
    assert a['1042']['severity'] == 'urgent' and a['1042']['revised_at'] is None
    assert a['1044']['severity'] == 'urgent'


def test_completed_orders_never_flagged(tmp_path):
    fresh(tmp_path)
    with database.connect() as db:
        db.execute("UPDATE orders SET status='handed_off' WHERE id='1043'")
    say("We're out of chicken.")
    assert '1043' not in alerts()


def test_acknowledgement_and_reopen_on_change(tmp_path):
    fresh(tmp_path)
    say("We're out of chicken.")
    a = alerts()['1043']
    assert a['status'] == 'new'
    store.set_alert_status('1043', 'acknowledged', a['signature'])
    assert alerts()['1043']['status'] == 'acknowledged'
    say('The fryer is ten minutes behind.')
    assert alerts()['1043']['status'] == 'new'                         # situation changed -> needs attention again
    with pytest.raises(ValueError):
        store.set_alert_status('1043', 'auto_everything', 'x')


def test_nothing_is_cancelled_or_rescheduled(tmp_path):
    fresh(tmp_path)
    before = [(o['id'], o['pickup_at'], o['status'], o['modifications_verified'], o['allergies_verified']) for o in fetch_orders()]
    say("We're out of chicken and the fryer is ten minutes behind.")
    after = [(o['id'], o['pickup_at'], o['status'], o['modifications_verified'], o['allergies_verified']) for o in fetch_orders()]
    assert before == after
