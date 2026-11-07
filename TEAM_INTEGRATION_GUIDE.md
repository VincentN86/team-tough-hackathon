# RushReady — Team Integration Guide (two-role app + Feature 3)

Branch: `liz-features`. Stack: Python + Streamlit + SQLite. (The earlier React prototype in `src/features/communication/` is
obsolete and not used by the app; it is kept only until the team agrees to delete it.)

## Ownership (who may edit what) and status of the proposed redesign
| Requested change | Feature owner | Existing file | Proposed file | Shared edit needed? | Status |
|---|---|---|---|---|---|
| Voice, parser, incidents, server alerts, ETAs/messages | **Feature 3 (Liz)** | `rushready/features/communication/*` | same | No | **Done + tested** |
| Item-level delays ("pizza +10", "burger ready in 10") | Feature 3 | `features/communication/{interpret,store,impact}.py` | same | No (scheduler untouched) | **Done + tested** |
| Role picker, header switch, role workspaces | Feature 1 / app shell | `rushready/roles.py`, `app.py` | same | Yes (already done earlier, see below) | Done earlier |
| iPad-style frame, resizable chef split-screen | Feature 1 / app shell | `rushready/roles.py` | `rushready/shell.py` (proposed) | Yes: `roles.py` | **Needs approval, not started** |
| Priority score formula, modes, urgency explanations, ticket UI | **Feature 2** | `rushready/scheduler.py`, `app.py::screen_cook` | `rushready/features/prioritizer/` (proposed) | Yes: reads `scheduler`, replaces left pane | **Needs Feature 2 owner's approval, not started** |
| Packing checklist | Feature 4 | `app.py::screen_packer` | unchanged | No | Unchanged |

**Interface Feature 3 offers Feature 2 (read-only, not wired):** `features.communication.impact.eta_adjustments(orders, incidents, flags)` returns
`{order_id: extra_minutes}` for chef-reported *item-level* delays. `scheduler.schedule()` can't express these (it only knows station delays), so the
Chef queue's estimates do not reflect "the pizza is 10 minutes late" yet; the Server view does. Feature 2 can add these minutes to its estimates.

## Feature 3 additions in this round
- New issue type `item_delay` (menu item or ingredient): "extra N min" or "ready in N min". Stored in `comm_flags` (new columns `item`, `delay_minutes`, `mode`, auto-migrated).
- ETAs: baseline = `scheduler.schedule()`; item delay is added on top as `max(0, N - station delay already applied)` so nothing is counted twice.
- Server cards now show a data-generated headline sentence, a timing chip (on track / at risk / likely late / blocked) and an "N of M can still be completed on time" line.
- Tests: `tests/test_communication.py`, `tests/test_communication_items.py`, `tests/test_integration.py` (46 tests total incl. Vincent's 4).

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
python -m pytest -q                     # 75 tests (4 original + Feature 3 logic/phrasing + 3 integrated)
```

## Prompt to give a teammate's AI agent
> "Read `TEAM_INTEGRATION_GUIDE.md` and `rushready/roles.py`. Do not edit `rushready/features/communication/`. To add or move a screen, define a
> function in `app.py` and register it in `roles.py`. Keep using `database.py` and `scheduler.py`; don't add a second order store. Run `python -m pytest -q` before committing."


## Ownership map and pending proposals (added after the first review round)
| Requested change | Owner | Existing file | Status |
|---|---|---|---|
| Smarter phrasing, auto-publish by confidence, ETA revision, server messages, on-track/at-risk/late/blocked | **Feature 3 (Liz)** | `rushready/features/communication/*` | DONE, tested |
| Welcome screen, role picker, navigation | Feature 1 | `rushready/roles.py` (shared), `app.py` | exists; no change yet |
| iPad-style frame, resizable chef split screen | Feature 1 (shell) | none yet | **PROPOSED, needs approval** (new `rushready/shell.py`; `roles.render_kitchen` would call it) |
| Priority modes + transparent scoring formula + per-ticket reasons + richer ticket card | Feature 2 | `app.py::screen_cook`, `scheduler.py` | **PROPOSED, needs Feature 2 owner approval** (new isolated module; `scheduler.schedule()` public output unchanged) |
| Server packing flow polish | Feature 4 | `app.py::screen_packer`, `screen_front_desk` | **not started, needs Feature 4 owner approval** |

Feature 3 parser changes in this round (all in `interpret.py`): "chicken's out", bare "no chicken" (tentative), "can't make X anymore" (now clear),
"off the menu", "fries/burgers are going to be about N minutes" (ready-in), "fryer's out" = station down, supplies ("out of gloves") ignored,
spoken short order numbers ("order 42" -> the single open order ending in 42; ambiguous or unknown numbers still ask).
Interface for Feature 2 (read-only, not wired): `impact.eta_adjustments()`. Feature 3 does not touch the priority queue order.

## UI redesign: tablet shell, Front Desk workspace, design system
| Area | File | Owner | Notes |
|---|---|---|---|
| Design tokens + global compact CSS | `rushready/ui/theme.py`, `rushready/.streamlit/config.toml` | Main UI / shell | Features may use the CSS variables (`var(--rr-late, fallback)`), never import it |
| Landing screen | `rushready/landing.py` | Main UI | Two cards, no emojis |
| Top bar, secondary nav, kitchen two-pane layout, role switch | `rushready/roles.py` (rewritten) | Main UI / shared | Kitchen: Feature 2 queue left, Feature 3 voice right (pane-size control). Voice pane is always rendered so the mic keeps listening |
| Front Desk layout (order rows left, alerts right) | `rushready/frontdesk.py` | Main UI | Reads `fetch_orders` (core) + `order_alerts()` (Feature 3) only |
| Focused packing view | `rushready/packing.py` | **Feature 4 logic, presentation proposed** | Same DB functions and widget keys as `screen_packer`; original screen kept under Front Desk -> Classic. **Needs Feature 4 owner review** |
| Alert cards pane, `order_alerts()` | `features/communication/ui_server.py`, `pipeline.py`, `styles.py`, `__init__.py` | Feature 3 | New public API: `render_server_alerts(on_view)`, `order_alerts()` |
| `app.py` | Vincent's file | Shared | 2 edits only: `initial_sidebar_state='collapsed'`; removed the stacked title/caption (top bar replaces them) |

**Not changed (needs owner approval):** Feature 2's ticket cards (`screen_cook`) still use their original layout/emoji hints; the theme only compacts
default Streamlit widgets (metrics, alert boxes) so they fit the pane. Feature 2 priority modes and the scoring formula are still only proposed.

**Preview at iPad size:** run the app, open browser DevTools (F12) -> device toolbar (Ctrl+Shift+M) -> set 1024x768 or 1180x820.
The panes fill the viewport height and scroll inside themselves only when the window is >= 900px wide and >= 560px tall; smaller windows use normal
page flow (nothing is clipped).

**Verified in a real browser (headless Edge) at 1024x768, 1180x820, 1440x800 with a 12-order scenario:** no page scroll, no horizontal overflow,
focus ring on keyboard Tab, acknowledge/View Order work, 77 tests pass. **Limitations:** Streamlit has no draggable divider (pane size uses
Queue/Even/Voice presets); markdown HTML blocks need a `margin-bottom:1rem` because Streamlit adds `-1rem`; the Feature 2 queue pane is still long
and scrolls inside its pane; the microphone and the Chrome speech engine can't be tested headlessly.

## BREDDY rebrand + Kitchen redesign (latest)
**Brand/identity:** product name is BREDDY (user-visible only: landing, top bar, browser tab, sidebar title). Package/repo/DB/internal `rr_` names are unchanged.
Palette: white `#FFFFFF`, Cod Gray `#191919`, red `#FF3008` (primary actions + selected states). Font: Lexend (Google Fonts `@import` in `ui/theme.py`;
falls back to Segoe UI/Arial offline). Semantic colours (late crimson, blocked Cod Gray, risk amber, ok green) are deliberately NOT the brand red.
White-on-red is 3.7:1, so red buttons use bold 17px+ text; small text never uses brand red.

**Kitchen is one screen:** no navigation. Left pane = Feature 2 queue (+ collapsed "Incoming orders" = the old intake screen), right pane = Feature 3 voice
panel (+ collapsed "Manual report (original)" = Vincent's typed report). The Queue/Even/Voice selector is gone.

**Draggable divider:** `ui/splitpane.py` + `ui/splitter/index.html` (main UI). A zero-height Streamlit component whose JS reaches the parent page (Streamlit serves
component iframes same-origin), finds the panes by their `st-key-rr_pane_queue/voice` classes, overlays a pointer-event divider and resizes the columns live.
No reruns while dragging. Mouse/touch/pen drag, arrow keys, Enter/double-click reset, 340px/300px minimums, saved in localStorage, hidden under 900px wide.
**Fragility to know:** it depends on Streamlit keeping same-origin component iframes and the `st-key-` class + `stColumn` test-id. If a Streamlit upgrade breaks
it, the panes simply stay at 60/40 (nothing else depends on it).

| File | Owner | Change |
|---|---|---|
| `ui/theme.py`, `.streamlit/config.toml`, `landing.py`, `roles.py`, `ui/splitpane.py`, `ui/splitter/index.html` | Main UI | brand, palette, font, kitchen shell, divider |
| `app.py` | Shared | page title, sidebar title, `screen_cook`: header "Kitchen Tickets", the long caption moved into a "Help" popover, emojis removed from status chips/hints (visual only, **Feature 2 owner to review**) |
| `features/communication/voice_component/index.html`, `ui_kitchen.py`, `ui_server.py` | Feature 3 | red mic button, 3 states (Off/Listening/Processing), paragraph + "Nothing heard yet" removed, compact "Mic help", shorter labels |

## Combined BREADY integration

The repository root now launches the canonical `rushready/app.py` through a small wrapper. Feature 1 lives in `rushready/intake.py` and `intake.css`, uses the same SQLite order store as Kitchen, AI communication, packing, and Front Desk, and supports named recipients without changing stored statuses or schema. Internal `rr_` keys and `RUSHREADY_DB` remain unchanged.

The individual kitchen ticket view previously on `main` is retained in `rushready/tickets.py`, accessible under Kitchen → Individual kitchen tickets, with its shared Start/Ready actions. The feature2 browser prototype is preserved under `rushready/kitchen-display`; its in-memory demo remains separate from Streamlit.

Validation at integration: 106 Python tests and 48 kitchen-display JavaScript tests passed. Browser smoke checks covered the role shell, kitchen, intake details, and Front Desk using an isolated demo database. Live microphone recognition and external AI calls were not exercised.
