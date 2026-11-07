"""INTEGRATED tests: the real app.py (landing + shell + Front Desk + Vincent's screens + Feature 3) driven headlessly with AppTest.
Run: python -m pytest tests/test_integration.py -q   (no browser needed; the microphone and the CSS/layout can't be tested here —
see the browser checks described in TEAM_INTEGRATION_GUIDE.md)"""
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import database

APP = str(ROOT / 'app.py')


def boot(tmp_path):
    database.DB_PATH = str(tmp_path / 'int.db')
    database.init_db()
    return AppTest.from_file(APP, default_timeout=60).run()


def texts(at):
    return ' '.join(e.value for group in (at.markdown, at.subheader, at.header, at.title, at.caption) for e in group)


def rows(sql):
    with database.connect() as db:
        return [dict(r) for r in db.execute(sql)]


def click(at, label):
    [b for b in at.button if b.label == label][0].click().run()


def press(at, key):
    [b for b in at.button if b.key == key][0].click().run()


def alert_cards(at):
    return [m.value for m in at.markdown if "class='rra " in m.value]


def report_box(at):
    return at.text_input(key='vc_typed_text')


def role(at):
    return at.session_state['rr_role']


def test_full_workflow(tmp_path):
    at = boot(tmp_path)
    assert not at.exception
    # 1) landing screen with both roles, nothing else yet
    labels = [b.label for b in at.button]
    assert 'Enter Kitchen' in labels and 'Enter Front Desk' in labels
    assert 'Voice Communication' not in texts(at)

    # 2) Kitchen: Vincent's prioritized tickets (left) + Feature 3 voice panel (right)
    click(at, 'Enter Kitchen')
    assert not at.exception and role(at) == 'kitchen'
    t = texts(at)
    assert 'Priority 1' in t and 'Voice Communication' in t
    assert 'BREADY' in t and 'RushReady' not in t                    # rebrand
    assert 'Incoming orders' not in [b.label for b in at.button]      # no separate navigation: it is a collapsed section now
    assert not at.get('button_group') or all(g.options != ['Queue', 'Even', 'Voice'] for g in at.get('button_group'))   # layout selector is gone
    for gone in ('Hands-free', 'Nothing heard yet', 'Queue', 'Typed report'):
        assert gone not in t, gone
    assert 'Incoming orders' in [e.label for e in at.expander] and 'Manual report (original)' in [e.label for e in at.expander]
    assert 'Mark Packed & Sealed' not in t                          # packing belongs to the Front Desk

    # 3) chef reports a shortage by typed text (same pipeline as speech) — no confirm/publish button needed
    report_box(at).set_value("We're out of chicken and the fryer is ten minutes behind.")
    click(at, 'Send')
    assert not at.exception
    assert 'Sent to Front Desk' in texts(at)
    inc = rows('SELECT * FROM incidents WHERE active=1')
    assert sorted((i['ingredient'], i['station'], i['delay_minutes']) for i in inc) == [('', 'Fryer', 10), ('chicken', '', 0)]

    # 4) switch roles: data preserved, alerts + orders visible in the two Front Desk panes
    click(at, 'Switch to Front Desk')
    assert not at.exception and role(at) == 'server'
    cards = alert_cards(at)
    assert any("#1043" in c and 'Blocked' in c for c in cards)       # chicken order blocked
    assert any("#1042" in c for c in cards)                          # fryer delay hits the burger+fries order
    assert not any("#1044" in c for c in cards)                      # salad/drink order is not alerted
    t = texts(at)
    assert 'Pack now' not in t and 'Awaiting food' in t and '#1044' in t   # nothing is cooked yet: 1044 is simply waiting

    # 5) acknowledge the blocked alert -> status changes and persists
    press(at, 'rrs_1043_acknowledged')
    assert [r['status'] for r in rows("SELECT * FROM comm_alerts WHERE order_id='1043'")] == ['acknowledged']
    assert any("#1043" in c and 'Acknowledged' in c for c in alert_cards(at))

    # 6) unaffected order 1044: kitchen marks both items ready, then the Front Desk packs it from the order row
    click(at, 'Switch to Kitchen')
    items = [i for o in database.fetch_orders() if o['id'] == '1044' for i in o['items']]
    for it in items:
        press(at, f"ready_{it['id']}")
    click(at, 'Switch to Front Desk')
    assert 'Pack now' in texts(at)
    press(at, 'rr_open_1044')                                        # focused packing view opens in the same pane
    assert 'Back to orders' in [b.label for b in at.button] and alert_cards(at)   # alerts stay visible while packing
    for it in items:
        at.checkbox(key=f"packed_{it['id']}").check().run()
    at.checkbox(key='mod_1044').check().run()
    at.checkbox(key='allergy_1044').check().run()
    press(at, 'seal_1044')
    assert not at.exception

    # 7) shared state consistent; order 1044 is now in "Ready for handoff" and can be handed off from its row
    orders = {o['id']: o for o in database.fetch_orders()}
    assert orders['1044']['status'] == 'packed'
    assert orders['1043']['status'] == 'queued'                      # affected order untouched
    assert 'Ready for handoff' in texts(at)
    press(at, 'rr_open_1044')                                        # row action for a packed order = Hand Off
    assert {o['id']: o for o in database.fetch_orders()}['1044']['status'] == 'handed_off'
    assert len([i for i in database.fetch_incidents() if i['active']]) == 2
    assert len(database.fetch_orders()) == 4


def test_cannot_seal_until_everything_is_verified(tmp_path):
    at = boot(tmp_path)
    click(at, 'Enter Front Desk')
    press(at, 'rr_open_1044')
    press(at, 'seal_1044')                                           # nothing cooked, nothing ticked
    assert any('kitchen has not finished' in w.value for w in at.warning)
    assert {o['id']: o for o in database.fetch_orders()}['1044']['status'] == 'queued'


def test_role_switch_keeps_data_and_sidebar_reset_clears_feature_data(tmp_path):
    at = boot(tmp_path)
    click(at, 'Enter Front Desk')
    assert role(at) == 'server' and not at.exception
    click(at, 'Switch to Kitchen')
    assert role(at) == 'kitchen'
    report_box(at).set_value('The grill is broken.')
    click(at, 'Send')
    assert len(rows('SELECT * FROM comm_flags')) == 1
    click(at, 'Switch to Front Desk')
    assert len(rows('SELECT * FROM comm_flags')) == 1                # switching roles resets nothing
    click(at, 'Reset demo restaurant')
    assert len(rows('SELECT * FROM comm_flags')) == 0


def test_item_delay_reaches_front_desk_with_revised_time(tmp_path):
    at = boot(tmp_path)
    click(at, 'Enter Kitchen')
    report_box(at).set_value('The pizza will be delayed by 10 minutes')
    click(at, 'Send')
    assert not at.exception and 'Sent to Front Desk' in texts(at)
    click(at, 'Switch to Front Desk')
    t = texts(at)
    assert not at.exception
    assert 'Order #1045 is delayed' in t and 'pizza is 10 minutes behind' in t       # message built from the report
    assert 'Est ' in t and 'On time' in t                                              # revised ETA + on-time summary
    cards = alert_cards(at)
    assert len(cards) == 1 and '#1045' in cards[0]                                     # only the pizza order is alerted


def test_busy_shift_many_orders_and_alerts(tmp_path):
    """12 orders, an overdue one, blocked ones, a tentative alert, a multi-item order with modifiers."""
    at = boot(tmp_path)
    database.create_order('DoorDash', 'Delivery driver', 3, [('Burger', 3, 'No onions, extra pickles', ''), ('Fries', 2, '', ''), ('Drink', 3, '', '')])
    for source, mins, lines in [('Uber Eats', 30, [('Chicken Sandwich', 2, 'Spicy', '')]), ('Phone', 18, [('Pizza', 1, 'Half mushroom', 'Dairy allergy')]),
                                ('Website', 22, [('Salad', 2, '', '')]), ('In-person POS', 9, [('Burger', 1, '', '')]), ('DoorDash', 35, [('Pizza', 2, '', '')]),
                                ('Uber Eats', 28, [('Chicken Sandwich', 1, '', '')]), ('Website', 40, [('Burger', 2, '', '')])]:
        database.create_order(source, 'Pickup customer', mins, lines)
    assert len(database.fetch_orders()) == 12
    click(at, 'Enter Kitchen')
    report_box(at).set_value("We're out of chicken and the fryer is ten minutes behind")
    click(at, 'Send')
    report_box(at).set_value('I have no beef')                                        # tentative
    click(at, 'Send')
    click(at, 'Switch to Front Desk')
    assert not at.exception
    t = texts(at)
    for o in database.fetch_orders():                                                   # every order has a row
        assert f"#{o['id']}" in t
    cards = alert_cards(at)
    assert any('Blocked' in c for c in cards) and any('Tentative' in c for c in cards)
    assert any('sev-delayed' in c for c in cards)                                       # at least one late/delayed order
    rows_html = ' '.join(m.value for m in at.markdown if "class='fd-row" in m.value)
    assert 'Late ' in rows_html and 'Blocked' in rows_html and 'Allergy' in rows_html and 'Mods' in rows_html
    # alert -> View Order opens that order's packing view (alerts stay on screen)
    press(at, 'rrv_1043')
    assert 'Back to orders' in [b.label for b in at.button] and alert_cards(at)
    assert any('3× Burger' not in m.value and '1× Chicken Sandwich' in m.value for m in at.markdown)
    click(at, 'Back to orders')
    assert 'Awaiting food' in texts(at)


def test_individual_ticket_keeps_shared_workflow(tmp_path):
    at = boot(tmp_path)
    click(at, 'Enter Kitchen')
    at.selectbox(key='kitchen_ticket_picker').select('1044').run()
    assert not at.exception
    item = next(o for o in database.fetch_orders() if o['id'] == '1044')['items'][0]
    press(at, f"bt_start_{item['id']}")
    assert next(o for o in database.fetch_orders() if o['id'] == '1044')['status'] == 'cooking'
    press(at, f"bt_ready_{item['id']}")
    assert next(o for o in database.fetch_orders() if o['id'] == '1044')['items'][0]['status'] == 'ready'
