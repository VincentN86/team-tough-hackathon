"""Shared SQLite order store for a *single-instance demo* (not a production KDS)."""
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = os.getenv('RUSHREADY_DB', str(Path(__file__).parent / 'rushready.db'))
MENU = {
    'Burger': {'station': 'Grill', 'minutes': 10, 'ingredients': ['beef', 'bun', 'onion']},
    'Chicken Sandwich': {'station': 'Fryer', 'minutes': 12, 'ingredients': ['chicken', 'bun']},
    'Fries': {'station': 'Fryer', 'minutes': 5, 'ingredients': ['potato']},
    'Pizza': {'station': 'Oven', 'minutes': 20, 'ingredients': ['cheese', 'flour']},
    'Salad': {'station': 'Cold', 'minutes': 4, 'ingredients': ['lettuce']},
    'Drink': {'station': 'Drinks', 'minutes': 1, 'ingredients': []},
}
SOURCES = ['DoorDash', 'Uber Eats', 'In-person POS', 'Website', 'Phone']
RECIPIENTS = ['Delivery driver', 'Pickup customer', 'Dine-in server']
STATIONS = ['Grill', 'Fryer', 'Oven', 'Cold', 'Drinks']


def utcnow():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


@contextmanager
def connect():
    connection = sqlite3.connect(DB_PATH, timeout=12)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    connection.execute('PRAGMA busy_timeout=12000')
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS orders (
              id TEXT PRIMARY KEY, source TEXT NOT NULL, recipient TEXT NOT NULL,
              received_at TEXT NOT NULL, pickup_at TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'queued',
              modifications_verified INTEGER NOT NULL DEFAULT 0,
              allergies_verified INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS items (
              id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT NOT NULL,
              name TEXT NOT NULL, quantity INTEGER NOT NULL,
              station TEXT NOT NULL, prep_minutes INTEGER NOT NULL,
              ingredients TEXT NOT NULL DEFAULT '',
              modifier TEXT NOT NULL DEFAULT '', allergy TEXT NOT NULL DEFAULT '',
              status TEXT NOT NULL DEFAULT 'queued', pack_verified INTEGER NOT NULL DEFAULT 0,
              FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS incidents (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              created_at TEXT NOT NULL, raw_note TEXT NOT NULL,
              ingredient TEXT NOT NULL DEFAULT '', station TEXT NOT NULL DEFAULT '',
              delay_minutes INTEGER NOT NULL DEFAULT 0,
              active INTEGER NOT NULL DEFAULT 1
            );
            CREATE INDEX IF NOT EXISTS idx_items_order ON items(order_id);
        ''')
        total = db.execute('SELECT COUNT(*) AS count FROM orders').fetchone()['count']
    if not total:
        reset_demo()


def _insert_order(db, order_id, source, recipient, pickup_minutes, lines, received_offset=0):
    now = utcnow() + timedelta(minutes=received_offset)
    db.execute('''INSERT INTO orders (id,source,recipient,received_at,pickup_at)
                VALUES (?,?,?,?,?)''', (str(order_id), source, recipient,
                                        iso(now), iso(now + timedelta(minutes=pickup_minutes))))
    for line in lines:
        name, qty, modifier, allergy = line
        food = MENU[name]
        db.execute('''INSERT INTO items (order_id,name,quantity,station,prep_minutes,ingredients,modifier,allergy)
                      VALUES (?,?,?,?,?,?,?,?)''',
                   (str(order_id), name, int(qty), food['station'],food['minutes'],
                    ','.join(food['ingredients']),modifier,allergy))


def reset_demo():
    with connect() as db:
        db.execute('DELETE FROM items')
        db.execute('DELETE FROM orders')
        db.execute('DELETE FROM incidents')
        _insert_order(db,'1042','DoorDash','Delivery driver',19,[('Burger',2,'No onions',''),('Fries',1,'','')],-3)
        _insert_order(db,'1043','Uber Eats','Delivery driver',26,[('Chicken Sandwich',1,'Extra pickles',''),('Drink',1,'','')],-2)
        _insert_order(db,'1044','In-person POS','Dine-in server',12,[('Salad',1,'No nuts','Nut allergy: staff must verify'),('Drink',1,'','')],-1)
        _insert_order(db,'1045','Website','Pickup customer',22,[('Pizza',1,'Extra cheese','')])


def create_order(source, recipient, minutes_until_pickup, lines):
    if source not in SOURCES or recipient not in RECIPIENTS:
        raise ValueError('Invalid source or recipient type')
    if not lines or any(n not in MENU or int(q)<1 for n,q,_,_ in lines):
        raise ValueError('Choose at least one valid food item and quantity')
    with connect() as db:
        latest = db.execute("SELECT MAX(CAST(id AS INTEGER)) AS highest FROM orders").fetchone()['highest']
        order_id = str(max(latest or 1045,1045) + 1)
        _insert_order(db, order_id, source, recipient, int(minutes_until_pickup), lines)
    return order_id


def fetch_orders():
    with connect() as db:
        order_rows = db.execute('SELECT * FROM orders ORDER BY received_at,id').fetchall()
        item_rows = db.execute('SELECT * FROM items ORDER BY id').fetchall()
    orders = {r['id']: dict(r) for r in order_rows}
    for row in orders.values():
        row['items'] = []
    for item in item_rows:
        if item['order_id'] in orders:
            orders[item['order_id']]['items'].append(dict(item))
    return list(orders.values())


def fetch_incidents():
    with connect() as db:
        return [dict(row) for row in db.execute('SELECT * FROM incidents ORDER BY id DESC')]


def update_item(item_id, new_status):
    if new_status not in ('cooking','ready'):
        raise ValueError('Invalid item status')
    with connect() as db:
        row = db.execute('SELECT order_id,status FROM items WHERE id=?',(item_id,)).fetchone()
        if not row or row['status']=='ready':
            return
        order = db.execute('SELECT status FROM orders WHERE id=?',(row['order_id'],)).fetchone()
        if order['status'] in ('packed','handed_off'):
            return
        db.execute('UPDATE items SET status=? WHERE id=?',(new_status,item_id))
        rows = db.execute('SELECT status FROM items WHERE order_id=?',(row['order_id'],)).fetchall()
        state = ('ready_to_pack' if all(x['status']=='ready' for x in rows)
                 else 'cooking' if any(x['status']!='queued' for x in rows) else 'queued')
        db.execute('UPDATE orders SET status=? WHERE id=?',(state,row['order_id']))


def verify_item_packed(item_id, verified):
    with connect() as db:
        db.execute('''UPDATE items SET pack_verified=? WHERE id=? AND status='ready'
                      AND order_id IN (SELECT id FROM orders WHERE status NOT IN ('packed','handed_off'))''',
                   (int(bool(verified)),int(item_id)))


def verify_special(order_id, kind, verified):
    if kind not in ('modifications_verified','allergies_verified'):
        raise ValueError('Unknown confirmation')
    with connect() as db:
        db.execute(f"UPDATE orders SET {kind}=? WHERE id=? AND status NOT IN ('packed','handed_off')",
                   (int(bool(verified)),str(order_id)))


def seal_order(order_id):
    """Staff-initiated confirmation; never infer this from AI or a photo."""
    with connect() as db:
        order = db.execute('SELECT * FROM orders WHERE id=?',(str(order_id),)).fetchone()
        if not order or order['status']!='ready_to_pack':
            return False, 'The kitchen has not finished every item.'
        items = db.execute('SELECT * FROM items WHERE order_id=?',(str(order_id),)).fetchall()
        if not items or not all(x['status']=='ready' and x['pack_verified'] for x in items):
            return False, 'Verify every item on the packing checklist.'
        if any(x['modifier'].strip() for x in items) and not order['modifications_verified']:
            return False, 'A staff member must confirm the modifications.'
        if any(x['allergy'].strip() for x in items) and not order['allergies_verified']:
            return False, 'A staff member must independently check allergy instructions.'
        db.execute("UPDATE orders SET status='packed' WHERE id=?",(str(order_id),))
        return True, 'Order marked packed and ready for handoff.'


def handoff_order(order_id):
    with connect() as db:
        cur = db.execute("UPDATE orders SET status='handed_off' WHERE id=? AND status='packed'", (str(order_id),))
        return cur.rowcount == 1


def add_incident(note, ingredient='', station='', delay_minutes=0):
    if station and station not in STATIONS:
        raise ValueError('Unknown station')
    with connect() as db:
        db.execute('''INSERT INTO incidents (created_at,raw_note,ingredient,station,delay_minutes)
                      VALUES (?,?,?,?,?)''', (iso(utcnow()),note[:700],ingredient.lower().strip(),station,
                                           max(0,min(120,int(delay_minutes)))))


def resolve_incident(incident_id):
    with connect() as db:
        db.execute('UPDATE incidents SET active=0 WHERE id=?',(incident_id,))
