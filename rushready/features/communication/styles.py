"""VISUAL STYLING for Feature 3 (alert cards, voice feed rows).  Owner: Feature 3 (Liz)

Colours come from the shared RushReady CSS variables (--rr-late, --rr-risk ...). The second argument of var() is a fallback, so this
feature still looks right when run without the main app's theme. Edit SEVERITY for the label shown on each alert, CSS for spacing/shape.
"""
import streamlit as st

# severity -> (short label, css class for the pill)
SEVERITY = {
    'urgent':   ('Blocked / needs action', 'blocked'),
    'delayed':  ('Delayed', 'late'),
    'possible': ('Tentative', 'tentative'),
    'watch':    ('Watch', 'risk'),
    'on_track': ('On track', 'ok'),
}
STATUS_LABEL = {'new': 'New', 'acknowledged': 'Acknowledged', 'customer_contacted': 'Customer contacted',
                'awaiting_response': 'Awaiting customer', 'resolved': 'Resolved'}

CSS = '''<style>
/* ---- alert card (front desk) ---- */
.rra{border-left:4px solid var(--rr-line,#e3e1db);padding:6px 12px;background:var(--rr-panel,#fff);border-radius:0 8px 8px 0;margin:0 0 1rem}   /* 1rem bottom: Streamlit markdown has margin-bottom:-1rem */
.rra.sev-urgent{border-left-color:var(--rr-blocked-bg,#1f2937)}
.rra.sev-delayed{border-left-color:var(--rr-late,#b42318)}
.rra.sev-watch{border-left-color:var(--rr-risk,#93370d)}
.rra.sev-possible{border-left:4px dashed var(--rr-tentative,#475467)}
.rra.handled{opacity:.72}                     /* acknowledged / in progress: quieter, but still readable */
.rra-top{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.rra-id{font-weight:800;font-size:1.05rem}
.rra-src,.rra-state{font-size:.8rem;color:var(--rr-muted,#66645f)}
.rra-state{margin-left:auto;font-weight:600}
.rra-msg{margin:2px 0;font-weight:600;font-size:.95rem;line-height:1.3}
.rra-eta{font-size:.9rem;font-variant-numeric:tabular-nums}
.rra-do{font-size:.8rem;color:var(--rr-muted,#66645f);margin-top:2px}
.rra-sum{display:block;line-height:26px;font-size:.85rem;color:var(--rr-muted,#66645f)}
.rra-sum .rr-pill{margin-left:4px}
/* ---- voice feed rows (chef) ---- */
.rr-feed{border-left:4px solid var(--rr-line,#d0d5dd);padding:4px 10px;margin:4px 0;background:var(--rr-bg,#f7f8fa);border-radius:0 6px 6px 0;font-size:.9rem}
.rr-feed.published{border-color:var(--rr-ok,#067647)}.rr-feed.provisional{border-color:var(--rr-risk,#93370d)}
.rr-feed.clarify{border-color:var(--rr-late,#b42318)}.rr-feed.ignored,.rr-feed.repeat{opacity:.7}
</style>'''


def inject_styles():
    st.markdown(CSS, unsafe_allow_html=True)
