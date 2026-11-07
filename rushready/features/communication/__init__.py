"""Feature 3 — AI Voice Communication Agent (owner: Liz).

PUBLIC API — the rest of RushReady should only import these names:
    render_voice_panel(key, model)   chef-side microphone + live feed        (ui_kitchen.py)
    render_server_alerts()           front-desk dashboard + alert cards      (ui_server.py)
    reset_feature_data()             clear this feature's tables on demo reset (store.py)
Everything else is internal. See README.md in this folder.

Pipeline (each stage is its own module so it can be debugged/edited alone):
    voice_component/index.html  speech -> text (browser)
    interpret.py                text -> structured issues + confidence
    impact.py                   issues -> affected orders, severity, ETAs (reuses scheduler.schedule)
    store.py                    publish by confidence into the shared SQLite DB (reuses incidents table)
    ui_server.py                reads the DB and shows actions
"""
from .store import reset_feature_data  # noqa: F401
from .ui_kitchen import render_voice_panel  # noqa: F401
from .ui_server import render_server_alerts  # noqa: F401
