# Feature 3 — AI Voice Communication Agent (owner: Liz)

Chef talks → relevant facts are extracted → matched to open orders → published to the Front Desk automatically.
Everything lives in this folder; the main app only calls three functions (see `__init__.py`).

## Pipeline (one module per stage — edit stages independently)
| Stage | File | What it does |
|---|---|---|
| 1 Speech → text | `voice_component/index.html` | Browser speech recognition. Start once; stays on, restarts itself after quiet spells; each finished sentence is sent immediately. Pause any time. |
| 2 Text → issues | `interpret.py` | Rule-based parser + optional OpenRouter AI (validated). Gives every issue a **confidence**. |
| 3 Issues → orders | `impact.py` | Deterministic matching; timing comes from `scheduler.schedule()` (no second scheduler). |
| 4 Publish | `store.py`, `pipeline.py` | Writes by confidence into the shared SQLite DB; duplicates, undo, resolve. |
| 5 Server screen | `ui_server.py` | Auto-refreshing (3 s) dashboard, alert cards, buttons. |
| Chef screen | `ui_kitchen.py` | Mic panel, typed fallback, "what I did" feed, Undo, advisories. |
| Look & colors | `styles.py` | Severity labels/colors. |

## What happens by confidence
| Confidence | Example | Result |
|---|---|---|
| high | "We're out of chicken." / "Fryer's ten minutes behind." | Published automatically as a real incident (affects estimates). |
| medium | "I have no chicken." / "No cooked chicken ready." / "Fryer is running slow." | Published as a **possible issue**: server sees "confirm with kitchen"; ETAs and order status are NOT changed. Chef can confirm or dismiss with one tap. |
| low | "We're running behind." / "Order 999 needs a remake" (no such order) | Nothing stored; light "didn't catch that" note. |
| none | "It's hot in here, someone turn on the fan." | Ignored. |

Automatic publishing never cancels an order, contacts a customer, changes a promised pickup time, or marks anything resolved by staff.
Those stay manual buttons on the server alert card. Saying "the fryer is back to normal" resolves the matching fryer incident; **Undo** reverses any report.

## Where to change things
| I want to change… | Edit |
|---|---|
| Microphone button, labels, listening behaviour | `voice_component/index.html` |
| Phrases the system understands, stations, number words | `interpret.py` → tables at the top, `interpret_rules()` |
| AI prompt / when the AI is called | `interpret.py` → `LLM_PROMPT`, `interpret()`, `looks_operational()` |
| What each confidence level does | `store.py` → `_apply()` |
| Severity levels, suggested actions, reason wording | `impact.py` → `build_alerts()` |
| Chef panel layout / feed / advisories | `ui_kitchen.py` |
| Server dashboard, alert cards, counters, refresh speed | `ui_server.py` (`REFRESH`) |
| Colors and labels | `styles.py` |
| Which screens each role sees, welcome page, role switch | `../../roles.py` (shared) |

## Reused from the main app (not duplicated)
`database.fetch_orders / fetch_incidents / add_incident / resolve_incident / connect`, `scheduler.schedule`, `ai_agent._request` (OpenRouter), the sidebar `KEY`/`MODEL`.
New tables (additive): `comm_flags`, `comm_alerts`, `comm_reports` — created automatically; existing tables are untouched.

## Tests
`python -m pytest tests/test_communication.py -q` (logic only, no UI) · `python -m pytest tests/test_integration.py -q` (whole app, headless).

## Honest limits
- Listening works only while the tab is open and Listening is ON (browser feature, Chrome/Edge). It is not background/always-on listening, and browsers may send audio to their speech vendor.
- The microphone itself can't be exercised by automated tests; typed input uses the identical pipeline and is tested.
- The rule parser is English, pattern-based. The AI path is untested without a real API key.
- Two browser sessions share the same SQLite file via the same running server; the Server view polls every 3 s. Not tested across different machines.
