"""STAGE 4 — ALERT PUBLISHING / PERSISTENCE.  Owner: Feature 3 (Liz)

Reuses Vincent's `incidents` table (via database.add_incident / resolve_incident) for CONFIRMED station delays and
ingredient shortages, so his scheduler keeps working unchanged. Adds three small tables of our own:
  comm_flags    — extra issue kinds (station down, remake) and PROVISIONAL advisories (never affect ETAs)
  comm_alerts   — server acknowledgement status per order
  comm_reports  — what the chef said + what we did, with an undo recipe

Edit here to change: what each confidence level does (_apply), duplicate rules, undo behaviour.
"""
import json

from database import add_incident, connect, fetch_incidents, iso, resolve_incident, utcnow

PROVISIONAL, CONFIRMED = 'provisional', 'confirmed'
CHANGED = ('published', 'provisional', 'updated', 'resolved')  # outcomes that changed stored state


def init_tables():
    with connect() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS comm_flags (
              id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL,
              ingredient TEXT NOT NULL DEFAULT '', station TEXT NOT NULL DEFAULT '',
              order_id TEXT NOT NULL DEFAULT '', raw_note TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
              certainty TEXT NOT NULL DEFAULT 'confirmed',
              item TEXT NOT NULL DEFAULT '', delay_minutes INTEGER NOT NULL DEFAULT 0, mode TEXT NOT NULL DEFAULT 'extra');
            CREATE TABLE IF NOT EXISTS comm_alerts (
              order_id TEXT PRIMARY KEY, status TEXT NOT NULL, signature TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS comm_reports (
              id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, transcript TEXT NOT NULL,
              summary TEXT NOT NULL, affected INTEGER NOT NULL DEFAULT 0,
              undo TEXT NOT NULL DEFAULT '[]', undone INTEGER NOT NULL DEFAULT 0);
        ''')
        # tolerate a DB created by an earlier version of this feature
        for table, col, ddl in (('comm_flags', 'certainty', "TEXT NOT NULL DEFAULT 'confirmed'"),
                                ('comm_flags', 'item', "TEXT NOT NULL DEFAULT ''"),
                                ('comm_flags', 'delay_minutes', 'INTEGER NOT NULL DEFAULT 0'),
                                ('comm_flags', 'mode', "TEXT NOT NULL DEFAULT 'extra'"),
                                ('comm_reports', 'undo', "TEXT NOT NULL DEFAULT '[]'"),
                                ('comm_reports', 'undone', 'INTEGER NOT NULL DEFAULT 0')):
            if col not in [r['name'] for r in db.execute(f'PRAGMA table_info({table})')]:
                db.execute(f'ALTER TABLE {table} ADD COLUMN {col} {ddl}')


def reset_feature_data():
    """Called by app.py's 'Reset demo restaurant' so stale alerts don't outlive the orders."""
    init_tables()
    with connect() as db:
        for t in ('comm_flags', 'comm_alerts', 'comm_reports'):
            db.execute(f'DELETE FROM {t}')


# ------------------------------------------------------------------ reads ----
def _rows(sql, args=()):
    with connect() as db:
        return [dict(r) for r in db.execute(sql, args)]


def fetch_flags():
    return _rows('SELECT * FROM comm_flags ORDER BY id DESC')


def fetch_reports(limit=30):
    return _rows('SELECT * FROM comm_reports ORDER BY id DESC LIMIT ?', (limit,))


def fetch_alert_rows():
    return {r['order_id']: r for r in _rows('SELECT * FROM comm_alerts')}


def describe(i):
    t = i['type']
    return {
        'ingredient_unavailable': f"{i['ingredient']} unavailable",
        'ingredient_low': f"{i['ingredient']} running low",
        'prep_wait': f"cooked {i['ingredient']} not ready yet",
        'order_issue': f"{i['ingredient'] or 'item'} missing on order #{i['order_id']}",
        'station_delay': f"{i['station']} {i['delay_minutes']} min behind",
        'item_delay': (f"{i['item']} ready in {i['delay_minutes']} min" if i.get('mode') == 'ready_in' and i['delay_minutes']
                       else f"{i['item']} +{i['delay_minutes']} min" if i['delay_minutes'] else f"{i['item']} may be late (no duration)"),
        'delay_unknown': f"{i['station'] or 'a station'} behind (no duration)",
        'station_down': f"{i['station']} down",
        'order_remake': f"order #{i['order_id']} remake",
        'resolve_station': f"{i['station']} back to normal",
        'resolve_ingredient': f"{i['ingredient']} available again",
    }[t]


# ---------------------------------------------------------------- low level ---
def _set_inc_active(inc_id, v):
    with connect() as db:
        db.execute('UPDATE incidents SET active=? WHERE id=?', (v, inc_id))


def _set_inc_delay(inc_id, minutes, note=None):
    with connect() as db:
        db.execute('UPDATE incidents SET delay_minutes=? WHERE id=?', (minutes, inc_id))


def _set_flag_active(flag_id, v):
    with connect() as db:
        db.execute('UPDATE comm_flags SET active=? WHERE id=?', (v, flag_id))


def _active_incidents():
    return [x for x in fetch_incidents() if x['active']]


def _new_incident(note, ingredient='', station='', delay=0):
    add_incident(note, ingredient=ingredient, station=station, delay_minutes=delay)
    return max(x['id'] for x in fetch_incidents())


def _add_flag(kind, note, certainty, ingredient='', station='', order_id='', item='', delay=0, mode='extra'):
    with connect() as db:
        cur = db.execute('INSERT INTO comm_flags (kind,ingredient,station,order_id,raw_note,created_at,certainty,item,delay_minutes,mode) '
                         'VALUES (?,?,?,?,?,?,?,?,?,?)',
                         (kind, ingredient, station, order_id, note[:700], iso(utcnow()), certainty, item, delay, mode))
        return cur.lastrowid


def _set_flag_delay(flag_id, minutes, created_at):
    with connect() as db:
        db.execute('UPDATE comm_flags SET delay_minutes=?, created_at=? WHERE id=?', (minutes, created_at, flag_id))


def _find_flags(kinds, ingredient=None, station=None, order_id=None, item=None):
    out = []
    for f in fetch_flags():
        if not f['active'] or f['kind'] not in kinds:
            continue
        if ingredient is not None and f['ingredient'] != ingredient:
            continue
        if station is not None and f['station'] != station:
            continue
        if order_id is not None and f['order_id'] != order_id:
            continue
        if item is not None and f['item'] != item:
            continue
        out.append(f)
    return out


def _retire(flags, undo):
    for f in flags:
        _set_flag_active(f['id'], 0)
        undo.append(['flag_active', f['id'], 1])  # undo recipe: turn it back on


# ----------------------------------------------------------------- the policy --
def _apply(i, note, undo):
    """Apply ONE interpreted issue according to its confidence. Returns an outcome string.
    Nothing here ever cancels an order, contacts a customer, or touches promised pickup times."""
    t, conf = i['type'], i['confidence']
    if conf == 'low':
        return 'clarify'  # never stored

    # ---- recoveries ("fryer is back to normal", "chicken is back")
    if t == 'resolve_station':
        hit_i = [x for x in _active_incidents() if x['station'] == i['station']]
        hit_f = _find_flags(('delay_unknown', 'station_down'), station=i['station'])
        for x in hit_i:
            resolve_incident(x['id'])
            undo.append(['inc_active', x['id'], 1])
        _retire(hit_f, undo)
        return 'resolved' if hit_i or hit_f else 'nothing_to_resolve'
    if t == 'resolve_ingredient':
        hit_i = [x for x in _active_incidents() if x['ingredient'] == i['ingredient']]
        hit_f = _find_flags(('ingredient_unavailable', 'ingredient_low', 'prep_wait'), ingredient=i['ingredient'])
        for x in hit_i:
            resolve_incident(x['id'])
            undo.append(['inc_active', x['id'], 1])
        _retire(hit_f, undo)
        return 'resolved' if hit_i or hit_f else 'nothing_to_resolve'

    # ---- HIGH confidence -> confirmed
    if conf == 'high':
        if t == 'ingredient_unavailable':
            if [x for x in _active_incidents() if x['ingredient'] == i['ingredient']]:
                return 'duplicate'
            _retire(_find_flags(('ingredient_unavailable', 'ingredient_low'), ingredient=i['ingredient']), undo)  # upgrade advisory
            undo.append(['inc_active', _new_incident(note, ingredient=i['ingredient']), 0])
            return 'published'
        if t == 'station_delay':
            same = [x for x in _active_incidents() if x['station'] == i['station'] and x['delay_minutes'] > 0]
            if same:
                if same[0]['delay_minutes'] == i['delay_minutes']:
                    return 'duplicate'  # repeating the same report must NOT add up
                undo.append(['inc_delay', same[0]['id'], same[0]['delay_minutes']])
                _set_inc_delay(same[0]['id'], i['delay_minutes'])  # same station, new number: REPLACE, never sum
                return 'updated'
            _retire(_find_flags(('delay_unknown',), station=i['station']), undo)
            undo.append(['inc_active', _new_incident(note, station=i['station'], delay=i['delay_minutes']), 0])
            return 'published'
        if t == 'item_delay' and i['delay_minutes'] > 0:
            same = _find_flags(('item_delay',), item=i['item'])
            confirmed = [f for f in same if f['certainty'] == CONFIRMED and f['mode'] == i['mode']]
            if confirmed:
                f = confirmed[0]
                if f['delay_minutes'] == i['delay_minutes'] and i['mode'] == 'extra':
                    return 'duplicate'  # same number again must NOT add up
                if f['delay_minutes'] == i['delay_minutes'] and i['mode'] == 'ready_in' and f['created_at'][:16] == iso(utcnow())[:16]:
                    return 'duplicate'
                undo.append(['flag_delay', f['id'], [f['delay_minutes'], f['created_at']]])
                _set_flag_delay(f['id'], i['delay_minutes'], iso(utcnow()))  # replace the number (and the clock for ready_in)
                return 'updated'
            _retire([f for f in same if f['certainty'] == PROVISIONAL], undo)  # upgrade an earlier "may be late"
            undo.append(['flag_active', _add_flag('item_delay', note, CONFIRMED, item=i['item'], station=i['station'],
                                                  delay=i['delay_minutes'], mode=i['mode']), 0])
            return 'published'
        if t in ('station_down', 'order_remake'):
            if _find_flags((t,), station=i['station'] if t == 'station_down' else None,
                           order_id=i['order_id'] if t == 'order_remake' else None):
                return 'duplicate'
            undo.append(['flag_active', _add_flag(t, note, CONFIRMED, station=i['station'], order_id=i['order_id']), 0])
            return 'published'

    # ---- MEDIUM confidence -> provisional advisory (does not change ETAs or block anything)
    covered = {
        'ingredient_unavailable': lambda: [x for x in _active_incidents() if x['ingredient'] == i['ingredient']]
        or _find_flags(('ingredient_unavailable',), ingredient=i['ingredient']),
        'ingredient_low': lambda: _find_flags(('ingredient_low',), ingredient=i['ingredient'])
        or [x for x in _active_incidents() if x['ingredient'] == i['ingredient']],
        'prep_wait': lambda: _find_flags(('prep_wait',), ingredient=i['ingredient']),
        'order_issue': lambda: _find_flags(('order_issue',), ingredient=i['ingredient'], order_id=i['order_id']),
        'item_delay': lambda: _find_flags(('item_delay',), item=i['item']),
        'delay_unknown': lambda: _find_flags(('delay_unknown',), station=i['station'])
        or [x for x in _active_incidents() if x['station'] == i['station'] and x['delay_minutes'] > 0],
    }
    if t in covered:
        if covered[t]():
            return 'duplicate'
        undo.append(['flag_active', _add_flag(t, note, PROVISIONAL, ingredient=i['ingredient'], station=i['station'],
                                              order_id=i['order_id'], item=i.get('item', ''), delay=0, mode='extra'), 0])
        return 'provisional'
    return 'clarify'  # e.g. a medium-confidence station_down: don't act on a guess


def publish(transcript, issues):
    """Apply interpreted issues. Returns (outcomes, undo_recipe)."""
    init_tables()
    outcomes, undo = [], []
    for i in issues:
        outcomes.append({'desc': describe(i), 'type': i['type'], 'confidence': i['confidence'],
                         'outcome': _apply(i, transcript, undo), 'note': i.get('note', ''), 'question': i.get('question', '')})
    return outcomes, undo


def record_report(transcript, outcomes, affected, undo):
    summary = '; '.join(f"{o['desc']} ({o['outcome']})" for o in outcomes if o['outcome'] in CHANGED + ('duplicate',))
    with connect() as db:
        cur = db.execute('INSERT INTO comm_reports (created_at,transcript,summary,affected,undo) VALUES (?,?,?,?,?)',
                         (iso(utcnow()), transcript[:700], summary[:500], affected, json.dumps(undo)))
        return cur.lastrowid


def undo_report(report_id):
    """Chef pressed Undo: replay the recipe backwards. Safe to call twice (second call does nothing)."""
    rows = _rows('SELECT * FROM comm_reports WHERE id=?', (report_id,))
    if not rows or rows[0]['undone']:
        return False
    for op, ident, val in reversed(json.loads(rows[0]['undo'])):
        if op == 'inc_active':
            _set_inc_active(ident, val)
        elif op == 'inc_delay':
            _set_inc_delay(ident, val)
        elif op == 'flag_active':
            _set_flag_active(ident, val)
        elif op == 'flag_delay':
            _set_flag_delay(ident, val[0], val[1])
    with connect() as db:
        db.execute('UPDATE comm_reports SET undone=1 WHERE id=?', (report_id,))
    return True


# ------------------------------------------------- chef/server follow-up actions --
def dismiss_flag(flag_id):
    _set_flag_active(flag_id, 0)


def resolve_flag(flag_id):
    _set_flag_active(flag_id, 0)


def confirm_flag(flag_id, minutes=0):
    """Chef explicitly confirms a provisional advisory. Returns True if it became a real incident."""
    f = next((x for x in fetch_flags() if x['id'] == flag_id and x['active']), None)
    if not f:
        return False
    if f['kind'] in ('ingredient_unavailable', 'ingredient_low') and not [x for x in _active_incidents() if x['ingredient'] == f['ingredient']]:
        _new_incident(f['raw_note'], ingredient=f['ingredient'])
    elif f['kind'] == 'delay_unknown' and f['station'] and 0 < minutes <= 120:
        same = [x for x in _active_incidents() if x['station'] == f['station'] and x['delay_minutes'] > 0]
        if same:
            _set_inc_delay(same[0]['id'], minutes)  # replace, never add
        else:
            _new_incident(f['raw_note'], station=f['station'], delay=minutes)
    elif f['kind'] == 'item_delay' and 0 < minutes <= 120:
        with connect() as db:  # the "may be late" advisory becomes a confirmed delay of N minutes
            db.execute("UPDATE comm_flags SET delay_minutes=?, certainty='confirmed', created_at=? WHERE id=?",
                       (minutes, iso(utcnow()), flag_id))
        return True
    else:
        return False
    _set_flag_active(flag_id, 0)
    return True


def set_alert_status(order_id, status, signature):
    """Server tapped a button. Only humans call this — nothing is ever auto-marked contacted/resolved."""
    if status not in ('acknowledged', 'customer_contacted', 'awaiting_response', 'resolved'):
        raise ValueError('bad status')
    with connect() as db:
        db.execute('INSERT INTO comm_alerts (order_id,status,signature,updated_at) VALUES (?,?,?,?) '
                   'ON CONFLICT(order_id) DO UPDATE SET status=excluded.status, signature=excluded.signature, updated_at=excluded.updated_at',
                   (str(order_id), status, signature, iso(utcnow())))
