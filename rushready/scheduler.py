"""Transparent, deterministic scheduling heuristics; NOT trained ML predictions."""
from collections import Counter
from datetime import datetime, timedelta, timezone
import math
from database import STATIONS

PACKING_MIN = 2


def _dt(value):
    dt = datetime.fromisoformat(value)
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def remaining_minutes(item):
    """Batching heuristic; assumes a single active line per station."""
    qty = item['quantity']
    return item['prep_minutes'] + max(0, qty-1) * max(1, item['prep_minutes']//3)


def incident_effects(order, active_incidents):
    """An ingredient shortage blocks work; a station delay shifts estimates."""
    matches=[]
    blocked=False
    for issue in active_incidents:
        for item in order['items']:
            if item['status']=='ready':
                continue
            terms = [s.strip().lower() for s in item['ingredients'].split(',')]
            if issue['ingredient'] and (issue['ingredient'].lower() in terms or issue['ingredient'].lower() in item['name'].lower()):
                blocked=True
                matches.append(issue)
                break
            if issue['station'] and issue['station']==item['station'] and issue['delay_minutes']:
                matches.append(issue)
                break
    return blocked, matches


def schedule(orders, incidents, now=None):
    now = now or datetime.now(timezone.utc)
    active = [i for i in incidents if i['active']]
    open_orders=[o for o in orders if o['status'] not in ('packed','handed_off')]
    station_delay={s:sum(i['delay_minutes'] for i in active if i['station']==s) for s in STATIONS}
    station_availability={s:now+timedelta(minutes=station_delay[s]) for s in STATIONS}

    def latest_start(o):
        todo=[remaining_minutes(x) for x in o['items'] if x['status']!='ready']
        effect=max((station_delay[x['station']] for x in o['items'] if x['status']!='ready'),default=0)
        return _dt(o['pickup_at']) - timedelta(minutes=(max(todo,default=0)+effect+PACKING_MIN))

    ranked = sorted(open_orders, key=lambda o:(latest_start(o),o['received_at']))
    results=[]
    for order in ranked:
        blocked, matching=incident_effects(order,active)
        finish=now
        for item in order['items']:
            if item['status']=='ready':
                continue
            if blocked and any(inc['ingredient'] and (inc['ingredient'] in item['ingredients'].split(',') or inc['ingredient'] in item['name'].lower()) for inc in matching):
                continue
            station=item['station']
            start=max(now,station_availability[station])
            finish_item=start+timedelta(minutes=remaining_minutes(item))
            station_availability[station]=finish_item
            finish=max(finish,finish_item)
        predicted = None if blocked else finish+timedelta(minutes=PACKING_MIN)
        slack = None if blocked else round((_dt(order['pickup_at'])-predicted).total_seconds()/60,1)
        results.append({**order,'blocked':blocked,'matching_incidents':matching,
                        'predicted_at':predicted,'slack':slack,
                        'late_minutes':None if blocked else max(0,math.ceil(-slack)),
                        'urgency': 'BLOCKED' if blocked else ('LATE' if slack<0 else 'RISK' if slack<5 else 'ON TRACK')})
    return results


def batch_hints(orders):
    counts=Counter()
    for o in orders:
        if o['status'] in ('packed','handed_off'):
            continue
        for item in o['items']:
            if item['status']!='ready':
                counts[(item['station'],item['name'])]+=item['quantity']
    return sorted([(station,name,n) for (station,name),n in counts.items() if n>=2],key=lambda x:-x[2])
