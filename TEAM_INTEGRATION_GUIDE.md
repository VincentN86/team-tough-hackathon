# RushReady — Team Integration Guide (two-role app + Feature 3)

Branch: `liz-features`. Stack: Python + Streamlit + SQLite. (The earlier React prototype in `src/features/communication/` is
obsolete and not used by the app; it is kept only until the team agrees to delete it.)

## What changed at a glance
RushReady now opens on a **role picker**: Chef/Kitchen or Packer/Server (stored per browser tab in `st.session_state['rr_role']`;
a demo switch, not authentication). Both roles read/write the same SQLite DB, so switching never resets anything.

| | Chef / Kitchen view | Packer / Server view |
|---|---|---|
| Top | **Feature 3 voice panel** (mic, typed fallback, feed, undo) | **Feature 3 dashboard** (counters, alert cards, activity) |
| Tabs | Prep queue & tickets (Feature 2) · Incoming orders (Feature 1) · Original typed chef report | Packing checklist (Feature 4) · Pickup & handoff · Take a new order (Feature 1) · Notes |

## File map
| Category | File | Purpose | Owner |
|---|---|---|---|
| Existing core | `rushready/database.py` | SQLite orders/items/incidents, status functions | Vincent/team (unchanged) |
| Existing core | `rushready/scheduler.py` | Priority, estimates, blocked orders | Vincent/team (unchanged) |
| Existing core | `rushready/ai_agent.py` | OpenRouter client, old parser, audio/photo | Vincent/team (unchanged) |
| Existing core | `rushready/tests/test_logic.py` | Original tests | Vincent/team (unchanged) |
| Integration | `rushready/app.py` | **Modified** — see below | Shared |
| Integration | `rushready/roles.py` | Role picker, header switcher, which screens each role sees | Shared (new) |
| Feature 3 | `rushready/features/communication/__init__.py` | Public API (3 functions) | Liz |
| Feature 3 | `.../interpret.py` | Text → structured issues + confidence (rules, optional AI, validation) | Liz |
| Feature 3 | `.../impact.py` | Matches issues to orders, severity, actions (uses `scheduler.schedule`) | Liz |
| Feature 3 | `.../store.py` | Publishing by confidence, duplicates, resolve, undo, `comm_*` tables | Liz |
| Feature 3 | `.../pipeline.py` | utterance → interpret → publish → feed entry | Liz |
| Feature 3 | `.../ui_kitchen.py`, `ui_server.py`, `styles.py` | Chef panel, server dashboard/cards, colors | Liz |
| Feature 3 | `.../voice_component/index.html` | Browser speech recognition component | Liz |
| Feature 3 | `.../README.md` | Where to edit what | Liz |
| Feature 3 tests | `rushready/tests/test_communication.py`, `test_integration.py` | Logic tests; whole-app headless test | Liz |
| Docs | `TEAM_INTEGRATION_GUIDE.md` | This file | Liz |

## Exactly what changed in Vincent's `app.py` (git diff shows it)
1. Two imports: `roles.ensure_role_selected / run_app`, `features.communication.reset_feature_data`.
2. `reset_feature_data()` added after `reset_demo()` in the sidebar reset button.
3. `ensure_role_selected()` inserted before `st.title(...)` (welcome screen; stops the script until a role is picked).
4. `tabs=st.tabs([...])` removed. Each `with tabs[k]:` became a function with the **same body, unchanged**:
   `screen_intake` (tab 0), `screen_cook` (1), `screen_packer` (2), `screen_front_desk` (3), `screen_notes` (4).
5. Tab 1's chef-agent half (everything after `cook_queue()`) moved to its own function `screen_legacy_agent` — code unchanged.
   It is still reachable (Kitchen → "Original typed report") and writes to the same `incidents` table.
6. A final `run_app({...screens...}, KEY, MODEL)` call.
**Consequence:** new screens must be registered in `roles.py`. If you add a tab, add a function in `app.py` and place it in `roles.render_kitchen` / `render_server`.
**Merge-conflict risk:** any edit to the lines above in `app.py` by teammates. Edits *inside* the tab bodies merge normally (indentation is unchanged), except lines near `cook_queue()` / the first `st.divider()` that I removed.

## Database changes (additive only)
Existing tables unchanged. New: `comm_flags` (station down, remake, provisional advisories), `comm_alerts` (server acknowledgement per order,
keyed by a signature that re-opens the alert when the situation changes), `comm_reports` (what the chef said, what happened, undo recipe).
Confirmed shortages/delays are stored in Vincent's `incidents` table so `scheduler.schedule` keeps working unmodified.
`init_tables()` creates/migrates them automatically.

## Reused APIs
`database.fetch_orders, fetch_incidents, add_incident, resolve_incident, connect, iso, utcnow, MENU, STATIONS` · `scheduler.schedule` · `ai_agent._request`
(private helper of Vincent's; if renamed, update `interpret.interpret_llm`) · sidebar `KEY` / `MODEL`.

## Rules other features should know
- One station's delay is **replaced**, never added, when re-reported (`store._apply`). Vincent's scheduler still sums active delays per station — so don't create two active delay incidents for one station elsewhere.
- Provisional advisories live only in `comm_flags` and never alter `scheduler` output.
- `comm_*` rows are cleared by "Reset demo restaurant".

## Running and testing
```
cd rushready
python -m venv .venv ; .venv\Scripts\activate
python -m pip install -r requirements.txt pytest
python -m streamlit run app.py          # http://localhost:8501
python -m pytest -q                     # 36 tests (4 original + 30 Feature 3 logic + 2 integrated)
```

## Prompt to give a teammate's AI agent
> "Read `TEAM_INTEGRATION_GUIDE.md` and `rushready/roles.py`. Do not edit `rushready/features/communication/`. To add or move a screen, define a
> function in `app.py` and register it in `roles.py`. Keep using `database.py` and `scheduler.py`; don't add a second order store. Run `python -m pytest -q` before committing."
