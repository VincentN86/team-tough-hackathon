"""Feature 1 regression checks. All writes use a temporary SQLite database."""
import sys
from copy import deepcopy
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import database
from intake import (SOURCE_COLORS, STATUS_LABELS, filter_orders, order_card,
                    recipient_label, summarize_orders)
from scheduler import schedule


@pytest.fixture
def demo(tmp_path, monkeypatch):
    monkeypatch.setattr(database, 'DB_PATH', str(tmp_path / 'intake_test.db'))
    database.init_db()
    return database.fetch_orders()


@pytest.mark.parametrize('source', database.SOURCES)
def test_every_source_persists_and_is_identified(demo, source):
    before = deepcopy(demo)
    recipient = recipient_label('Alex Chen', 'Pickup customer')
    order_id = database.create_order(source, recipient, 25,
                                    [('Burger', 2, 'No onions', 'Check bun ingredients')])
    records = database.fetch_orders()  # A new connection, not an in-memory result.
    assert [o for o in records if o['id'] != order_id] == before
    order = next(o for o in records if o['id'] == order_id)
    assert order['source'] == source
    assert order['recipient'] == 'Alex Chen · Pickup customer'
    assert order['status'] == 'queued'
    item = order['items'][0]
    assert (item['quantity'], item['modifier'], item['allergy']) == (2, 'No onions', 'Check bun ingredients')
    assert item['station'] == 'Grill' and item['prep_minutes'] == 10
    assert source in SOURCE_COLORS
    assert source in order_card(order)
    assert order_id in {o['id'] for o in filter_orders(records, source=source)}


def test_filter_search_sort_and_counts_do_not_mutate_records(demo):
    records = deepcopy(demo)
    assert len(filter_orders(records)) == 4
    assert [o['id'] for o in filter_orders(records, source='DoorDash')] == ['1042']
    assert [o['id'] for o in filter_orders(records, source='Uber Eats')] == ['1043']
    assert [o['id'] for o in filter_orders(records, query=' #1044 ')] == ['1044']
    assert len(filter_orders(records, query='DELIVERY DRIVER')) == 2
    assert filter_orders(records, query='does not exist') == []
    assert filter_orders(records, status='packed') == []
    assert filter_orders(records)[0]['id'] == '1045'
    assert filter_orders(records, sort='Oldest first')[0]['id'] == '1042'
    assert filter_orders(records, sort='Pickup deadline')[0]['id'] == '1044'
    assert summarize_orders(records)['active'] == 4
    assert summarize_orders(records)['sources']['Phone'] == 0
    assert records == demo
    assert filter_orders([]) == []
    assert summarize_orders([])['total'] == 0


def test_named_order_follows_existing_downstream_lifecycle(demo):
    order_id = database.create_order('Website', recipient_label('Jamie', 'Pickup customer'), 30,
                                    [('Salad', 1, 'No nuts', 'Nut allergy')])
    records = database.fetch_orders()
    assert filter_orders(records, query='jamie')[0]['id'] == order_id
    assert order_id in {o['id'] for o in schedule(records, [])}
    order = next(o for o in records if o['id'] == order_id)
    item_id = order['items'][0]['id']
    database.update_item(item_id, 'cooking')
    assert filter_orders(database.fetch_orders(), query=order_id)[0]['status'] == 'cooking'
    database.update_item(item_id, 'ready')
    assert filter_orders(database.fetch_orders(), query=order_id)[0]['status'] == 'ready_to_pack'
    database.verify_item_packed(item_id, True)
    assert not database.seal_order(order_id)[0]
    database.verify_special(order_id, 'modifications_verified', True)
    database.verify_special(order_id, 'allergies_verified', True)
    assert database.seal_order(order_id)[0]
    assert filter_orders(database.fetch_orders(), status='packed')[0]['id'] == order_id
    assert database.handoff_order(order_id)
    assert filter_orders(database.fetch_orders(), status='handed_off')[0]['id'] == order_id
    summary = summarize_orders(database.fetch_orders())
    assert summary['total'] == 5 and summary['active'] == 4
    assert set(STATUS_LABELS) == {'queued', 'cooking', 'ready_to_pack', 'packed', 'handed_off'}


@pytest.mark.parametrize('name', ['', '   ', 'a' * 81, 'Alex\nChen'])
def test_invalid_names(name):
    with pytest.raises(ValueError):
        recipient_label(name, 'Pickup customer')


@pytest.mark.parametrize('source,recipient,lines', [
    ('Unknown', 'Pickup customer', [('Burger', 1, '', '')]),
    ('Phone', 'Alex · Unknown', [('Burger', 1, '', '')]),
    ('Phone', ' · Pickup customer', [('Burger', 1, '', '')]),
    ('Phone', 'Pickup customer', []),
    ('Phone', 'Pickup customer', [('Unknown food', 1, '', '')]),
    ('Phone', 'Pickup customer', [('Burger', 0, '', '')]),
])
def test_invalid_intake_does_not_write(demo, source, recipient, lines):
    with pytest.raises(ValueError):
        database.create_order(source, recipient, 25, lines)
    assert database.fetch_orders() == demo


def test_cards_escape_input(demo):
    order = deepcopy(demo[0])
    order['recipient'] = '<script>alert(1)</script>'
    order['items'][0]['modifier'] = '<img src=x onerror=alert(1)>'
    html = order_card(order)
    assert '<script>' not in html and '<img' not in html
    assert '&lt;script&gt;' in html and '&lt;img' in html


def test_intake_ui_submission_and_reruns(demo):
    from streamlit.testing.v1 import AppTest

    # Test only Feature 1; do not load app.py or access its secret configuration.
    at = AppTest.from_string('from intake import render_intake\nrender_intake()').run()
    assert not at.exception

    def by_label(elements, label):
        return next(element for element in elements if element.label == label)

    by_label(at.button, 'Create incoming order').click().run()
    assert at.warning
    assert database.fetch_orders() == demo
    by_label(at.text_input, 'Recipient name').input('Taylor')
    by_label(at.selectbox, 'Order source').select('Website')
    by_label(at.number_input, 'Burger').set_value(2)
    by_label(at.text_input, 'Burger modification').input('No onions')
    by_label(at.button, 'Create incoming order').click().run()
    assert not at.exception
    assert len(database.fetch_orders()) == 5
    assert any('1046' in element.value for element in at.success)
    assert any('Taylor' in element.value for element in at.markdown)
    assert not any(element.label == 'Create incoming order' for element in at.button)
    for _ in range(2):
        at.run()
    assert len(database.fetch_orders()) == 5
    by_label(at.selectbox, 'Source').select('DoorDash').run()
    assert by_label(at.selectbox, 'Source').value == 'DoorDash'
    at.run()
    assert by_label(at.selectbox, 'Source').value == 'DoorDash'
    by_label(at.button, 'Start another order').click().run()
    assert by_label(at.text_input, 'Recipient name').value == ''
    assert by_label(at.number_input, 'Burger').value == 0
    assert len(database.fetch_orders()) == 5
