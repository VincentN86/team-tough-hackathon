"""STATUS COLORS & VISUAL STYLING for Feature 3 (alert banners, feed rows).  Owner: Feature 3 (Liz)
Edit SEVERITY to change labels/colors of alert cards. Edit CSS for spacing/shape."""
import streamlit as st

# severity -> (label shown on the card, banner color, banner text color)
SEVERITY = {
    'urgent':   ('URGENT',            '#c62828', '#ffffff'),
    'delayed':  ('DELAYED',           '#e65100', '#ffffff'),
    'possible': ('POSSIBLE ISSUE',    '#f9a825', '#1c2430'),
    'watch':    ('WATCH',             '#fbc02d', '#1c2430'),
    'on_track': ('ON TRACK',          '#2e7d32', '#ffffff'),
}
STATUS_LABEL = {'new': 'Needs Attention', 'acknowledged': 'Acknowledged', 'customer_contacted': 'Customer Contacted',
                'awaiting_response': 'Awaiting Customer Response', 'resolved': 'Resolved'}

CSS = '''<style>
.rr-banner{border-radius:10px;padding:10px 14px;font-weight:800;font-size:1.15rem;letter-spacing:.3px;margin-bottom:6px}
.rr-banner small{font-weight:500;opacity:.9;margin-left:8px}
.rr-feed{border-left:6px solid #98a2b3;padding:6px 12px;margin:6px 0;border-radius:6px;background:#f7f8fa}
.rr-feed.published{border-color:#2e7d32}.rr-feed.provisional{border-color:#f9a825}
.rr-feed.clarify{border-color:#e65100}.rr-feed.ignored,.rr-feed.repeat{border-color:#cfd4dc;opacity:.8}
.rr-pill{display:inline-block;padding:2px 10px;border-radius:999px;background:#e6e9ef;font-size:.75rem;font-weight:700}
</style>'''


def inject_styles():
    st.markdown(CSS, unsafe_allow_html=True)
