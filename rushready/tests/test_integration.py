"""INTEGRATED tests: the real app.py (roles + Vincent's screens + Feature 3) driven headlessly with Streamlit's AppTest.
Run: python -m pytest tests/test_integration.py -q   (does not need a browser; the microphone itself can't be tested here)"""
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


def test_full_workflow(tmp_path):
    at = boot(tmp_path)
    assert not at.exception
    # 1) welcome screen with both roles, nothing else yet
    labels = [b.label for b in at.button]
    assert 'Enter Kitchen' in labels and 'Enter Front Desk' in labels
    assert 'Priority 1' not in texts(at)

    # 2) Kitchen view: Vincent's prioritized tickets + Feature 3 voice panel
    click(at, 'Enter Kitchen')
    assert not at.exception
    t = texts(at)
    assert 'Current view: **Kitchen**' in t and 'Priority 1' in t and 'Tell the front desk' in t
    assert 'Packing verification' not in t                       # packing belongs to the server

    # 3) chef reports a shortage by typed text (same pipeline as speech) — no confirm/publish button needed
    at.text_input[0].set_value("We're out of chicken and the fryer is ten minutes behind.")
    click(at, 'Send')
    assert not at.exception
    assert 'Sent to Front Desk' in texts(at)
    with database.connect() as db:
        inc = [dict(r) for r in db.execute('SELECT * FROM incidents WHERE active=1')]
    assert sorted((i['ingredient'], i['station'], i['delay_minutes']) for i in inc) == [('', 'Fryer', 10), ('chicken', '', 0)]

    # 4) switch roles: data preserved, alerts visible
    click(at, 'Switch to Front Desk')
    assert not at.exception
    t = texts(at)
    assert 'Current view: **Front Desk**' in t
    assert 'URGENT — ORDER #1043' in t and 'ORDER #1042' in t
    assert 'ORDER #1044' in t or 'ON TRACK — ORDER #1044' in t
    assert 'Packing verification' in t

    # 5) acknowledge the urgent alert -> status changes and persists
    [b for b in at.button if b.key == 'rrs_1043_acknowledged'][0].click().run()
    assert [r['status'] for r in rows("SELECT * FROM comm_alerts WHERE order_id='1043'")] == ['acknowledged']

    # 6) unaffected order 1044: kitchen marks both items ready, packer completes the checklist
    click(at, 'Switch to Kitchen')
    items = [i for o in database.fetch_orders() if o['id'] == '1044' for i in o['items']]
    for it in items:
        [b for b in at.button if b.key == f"ready_{it['id']}"][0].click().run()
    click(at, 'Switch to Front Desk')
    for it in items:
        at.checkbox(key=f"packed_{it['id']}").check().run()
    at.checkbox(key='mod_1044').check().run()
    at.checkbox(key='allergy_1044').check().run()
    [b for b in at.button if b.key == 'seal_1044'][0].click().run()
    assert not at.exception

    # 7) shared state consistent
    orders = {o['id']: o for o in database.fetch_orders()}
    assert orders['1044']['status'] == 'packed'
    assert orders['1043']['status'] == 'queued'                  # affected order untouched
    assert orders['1043']['pickup_at'] and len(database.fetch_orders()) == 4
    assert len([i for i in database.fetch_incidents() if i['active']]) == 2


def test_role_switch_keeps_data_and_sidebar_reset_clears_feature_data(tmp_path):
    at = boot(tmp_path)
    click(at, 'Enter Front Desk')
    assert 'Current view: **Front Desk**' in texts(at) and not at.exception
    click(at, 'Switch to Kitchen')
    assert 'Current view: **Kitchen**' in texts(at)
    at.text_input[0].set_value('The grill is broken.')
    click(at, 'Send')
    assert len(rows('SELECT * FROM comm_flags')) == 1
    click(at, 'Reset demo restaurant')
    assert len(rows('SELECT * FROM comm_flags')) == 0
