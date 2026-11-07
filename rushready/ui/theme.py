"""SHARED DESIGN SYSTEM for BREADY (Kitchen + Front Desk + landing).  Owner: main BREADY UI (shell).  Not a feature package.

One place for design tokens + the global compact-tablet CSS. Features may *use* the CSS variables (e.g. `var(--rr-late, #b42318)`)
but must not import this file, so every feature stays independently runnable. (The `--rr-` prefix is an internal name, kept so nothing breaks.)

BRAND PALETTE (official): White #FFFFFF = panels / working surfaces, Cod Gray #191919 = text / dark surfaces, Red #FF3008 = primary actions + selected states.
LAYERS (so nothing blends into one white/black mass): light-grey page canvas -> white panels -> grey rows/inputs -> dark top bar and ticket rail.
FONT: Lexend (Google Fonts, loaded with @import in root_css(); falls back to Segoe UI / Arial if offline).

WHERE TO EDIT
    Colours / status colours ......... TOKENS
    Font ............................. FONT_FAMILY / FONT_IMPORT
    Spacing (4px scale), radii, sizes . SPACING / SIZES
    Streamlit's own primary colour .... rushready/.streamlit/config.toml ([theme] primaryColor — keep equal to TOKENS['accent'])
    Top bar / pane layout / scrolling . GLOBAL_CSS  (sections are commented)
    Breakpoints ....................... the @media blocks at the bottom of GLOBAL_CSS (900px wide / 560px tall = tablet workspace)

Semantic colours (never the brand red, so a warning is not mistaken for a primary action):
    late = deep crimson, blocked = Cod Gray fill, risk = amber, ok = green, info/tentative = neutral grey (tentative is dashed).
Every status also carries a TEXT label, so colour is never the only signal.
Contrast: Cod Gray on white 17:1. White on BREADY red is 3.7:1, so red buttons use bold 17px+ text (WCAG "large text" 3:1); small text never uses brand red.
"""
import re
from datetime import datetime, timezone

import streamlit as st

TOKENS = {
    'bg': '#eeeeee', 'panel': '#ffffff', 'surface': '#f5f5f5', 'surface-2': '#e2e2e2', 'line': '#c9c9c9', 'line-strong': '#767676', 'text': '#191919', 'muted': '#555555',
    'accent': '#ff3008', 'accent-hover': '#d92806', 'accent-tint': '#ffece8', 'focus': '#191919',
    'late': '#b42318', 'late-bg': '#fee4e2',
    'blocked': '#ffffff', 'blocked-bg': '#191919',
    'risk': '#93370d', 'risk-bg': '#fef0c7',
    'ok': '#067647', 'ok-bg': '#dcfae6',
    'tentative': '#3d3d3d', 'tentative-bg': '#e0e0e0',
}
FONT_FAMILY = '"Lexend","Segoe UI","Helvetica Neue",Arial,sans-serif'
FONT_IMPORT = "@import url('https://fonts.googleapis.com/css2?family=Lexend:wght@400;500;600;700;800&display=swap');"
SPACING = {1: '4px', 2: '8px', 3: '12px', 4: '16px', 6: '24px'}   # 4px scale: use var(--rr-s2) etc.
SIZES = {'btn-h': '44px', 'radius': '8px', 'radius-sm': '4px', 'font': '15px'}  # 44px = minimum comfortable touch target


# Streamlit's header is transparent and must not swallow clicks meant for our top bar / landing buttons; only the sidebar (settings)
# button stays clickable. The workspace top bar reserves 44px on its left for that button.
HEADER_CSS = ('[data-testid="stHeader"]{background:transparent !important;height:0 !important;min-height:0 !important;}'  # no white band
              '[data-testid="stHeader"],[data-testid="stHeader"] *{pointer-events:none;}'
              '[data-testid="stExpandSidebarButton"],[data-testid="stExpandSidebarButton"] *,[data-testid="stSidebarCollapsedControl"],'
              '[data-testid="stSidebarCollapsedControl"] *{pointer-events:auto;}')

# Lexend everywhere text appears. Material icon glyphs are excluded or they would turn into words.
FONT_CSS = ('html,body,[data-testid="stApp"],[data-testid="stApp"] :is(p,h1,h2,h3,h4,h5,h6,label,button,input,textarea,select,li,td,th,a,div,'
            'span:not([data-testid="stIconMaterial"])){font-family:var(--rr-font-family) !important;}')


def root_css():
    """@import + CSS variables + font + header rules. The landing screen and the workspaces both start from this."""
    light = ''.join(f'--rr-{k}:{v};' for k, v in TOKENS.items())
    sp = ''.join(f'--rr-s{k}:{v};' for k, v in SPACING.items())
    sz = ''.join(f'--rr-{k}:{v};' for k, v in SIZES.items())
    return f"{FONT_IMPORT}\n:root{{{light}{sp}{sz}--rr-font-family:{FONT_FAMILY};}}\n{FONT_CSS}\n{HEADER_CSS}\n"


GLOBAL_CSS = '''
/* ---------- BASE: white background, Cod Gray text, compact density ---------- */
[data-testid="stApp"]{background:var(--rr-bg);color:var(--rr-text);font-size:var(--rr-font);}
[data-testid="stSidebar"]{background:var(--rr-surface-2);}
div.block-container{max-width:100% !important;padding:var(--rr-s2) var(--rr-s4) 0 !important;}
[data-testid="stVerticalBlock"]{gap:var(--rr-s2);}
[data-testid="stExpandSidebarButton"]{position:fixed;top:14px;left:10px;z-index:100;}
h1,h2,h3,h4{letter-spacing:-0.01em;margin:0;padding:0;font-weight:700 !important;}
h3{font-size:1.1rem !important;}
h4{font-size:1rem !important;}
[data-testid="stCaptionContainer"],.stCaption{color:var(--rr-muted);}

/* ---------- BUTTONS: 44px touch targets; brand red = primary action; Cod Gray focus ring ---------- */
.stButton>button,[data-testid="stBaseButton-secondary"],[data-testid="stBaseButton-primary"],[data-testid="stPopover"] button{
  min-height:var(--rr-btn-h);border-radius:var(--rr-radius);font-weight:600;border:1.5px solid var(--rr-text);background:var(--rr-surface-2);color:var(--rr-text);}
.stButton>button:hover,[data-testid="stPopover"] button:hover{border-color:var(--rr-accent);background:#fff;color:var(--rr-text);}
[data-testid="stBaseButton-primary"]{background:var(--rr-accent) !important;border-color:var(--rr-accent) !important;color:#fff !important;
  font-weight:700;font-size:1.05rem;}
[data-testid="stBaseButton-primary"] p{color:#fff !important;font-size:1.05rem;font-weight:700;}
[data-testid="stBaseButton-primary"]:hover{background:var(--rr-accent-hover) !important;border-color:var(--rr-accent-hover) !important;}
button:disabled{opacity:.5;background:var(--rr-surface) !important;border-color:var(--rr-line) !important;}
.stButton>button:focus-visible,[data-testid="stPopover"] button:focus-visible,[data-testid="stCheckbox"] input:focus-visible+div,
[data-testid="stButtonGroup"] button:focus-visible{outline:3px solid var(--rr-focus);outline-offset:2px;}
/* segmented controls (navigation): selected = red-tinted fill + red edge, text stays Cod Gray */
[data-testid="stButtonGroup"] button{min-height:40px;background:#fff;color:var(--rr-text);border:1.5px solid var(--rr-line-strong);}
[data-testid="stBaseButton-segmented_controlActive"]{background:var(--rr-accent-tint) !important;border:1px solid var(--rr-accent) !important;
  color:var(--rr-text) !important;font-weight:700;}
[data-testid="stBaseButton-segmented_controlActive"] p,[data-testid="stBaseButton-segmented_controlActive"] *{color:var(--rr-text) !important;}
[data-testid="stCheckbox"] label{min-height:var(--rr-btn-h);align-items:center;}

/* ---------- TOP BAR (keyed container 'rr_topbar') ---------- */
.st-key-rr_topbar{background:var(--rr-text);border-radius:var(--rr-radius);padding:var(--rr-s2) var(--rr-s3) var(--rr-s2) 44px;}
.st-key-rr_topbar .rr-brand{color:#fff;}
.st-key-rr_topbar .rr-chips{color:#e6e6e6;}
.st-key-rr_topbar .rr-pill.blocked{background:#fff;color:var(--rr-text);}
.st-key-rr_topbar .stButton>button{background:#fff;border-color:#fff;}
.st-key-rr_topbar .stButton>button:hover{background:var(--rr-accent-tint);border-color:var(--rr-accent);}
[data-testid="stExpandSidebarButton"],[data-testid="stExpandSidebarButton"] *{color:#fff !important;}
.rr-brand,.rr-rolechip{white-space:nowrap;}
.rr-brand{font-size:1.35rem;font-weight:800;letter-spacing:.04em;margin-right:var(--rr-s2);text-transform:uppercase;}
.rr-rolechip{font-size:.8rem;font-weight:700;padding:2px 8px;border-radius:var(--rr-radius-sm);background:var(--rr-accent);color:var(--rr-text);}
.rr-chips{display:flex;gap:var(--rr-s2);flex-wrap:wrap;justify-content:flex-end;font-size:.85rem;color:var(--rr-muted);}

/* ---------- STATUS PILLS (shared by shell, Front Desk, Feature 3) ---------- */
.rr-pill{display:inline-block;padding:1px 8px;border-radius:var(--rr-radius-sm);font-size:.75rem;font-weight:700;line-height:1.5;white-space:nowrap;
  background:var(--rr-tentative-bg);color:var(--rr-tentative);}
.rr-pill.late{background:var(--rr-late-bg);color:var(--rr-late);}
.rr-pill.blocked{background:var(--rr-blocked-bg);color:var(--rr-blocked);}
.rr-pill.risk{background:var(--rr-risk-bg);color:var(--rr-risk);}
.rr-pill.ok{background:var(--rr-ok-bg);color:var(--rr-ok);}
.rr-pill.info{background:var(--rr-tentative-bg);color:var(--rr-text);}
.rr-pill.tentative{border:1px dashed var(--rr-tentative);}

/* ---------- COMPACT DEFAULT WIDGETS (so teammates' existing screens fit the tablet workspace without logic changes) ---------- */
[data-testid="stMetric"]{padding:6px 10px !important;border:1px solid var(--rr-line) !important;border-radius:var(--rr-radius) !important;background:var(--rr-surface);}
[data-testid="stMetricValue"]{font-size:1.5rem !important;}
[data-testid="stMetricLabel"] p{font-size:.8rem !important;}
[data-testid="stAlert"],[data-testid="stAlertContainer"]{padding:2px 8px !important;border-radius:var(--rr-radius) !important;min-height:0 !important;}
[data-testid="stAlert"] p{font-size:.9rem;}
/* info boxes (batching hints, modification notes) are neutral grey, not Streamlit blue; warning / error / success keep their own colours */
[data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]),[data-testid="stAlertContainer"]:has([data-testid="stAlertContentInfo"]){background:var(--rr-surface) !important;color:var(--rr-text) !important;}
[data-testid="stAlertContentInfo"] *{color:var(--rr-text) !important;}
[data-testid="stExpander"] details{border:1.5px solid var(--rr-line-strong);border-radius:var(--rr-radius);background:var(--rr-surface);}
[data-baseweb="input"],[data-baseweb="textarea"],[data-baseweb="select"] > div{background:#fff !important;border:1.5px solid var(--rr-line-strong) !important;border-radius:var(--rr-radius) !important;}
[data-testid="stExpander"] summary{min-height:var(--rr-btn-h);font-weight:600;}

/* ---------- PANES: panels that scroll INSIDE themselves (keyed containers named rr_pane_*) ---------- */
[class*="st-key-rr_pane_"]{background:var(--rr-panel);border:1.5px solid var(--rr-line);border-radius:var(--rr-radius);
  padding:var(--rr-s3);overflow-y:auto;}
/* the zero-height host of the draggable-divider component (see ui/splitpane.py) */
.st-key-rr_split_host{position:absolute !important;height:0 !important;width:0 !important;overflow:hidden;margin:0 !important;}

/* ---------- TABLET WORKSPACE: panes fill the viewport height so the PAGE itself does not scroll ----------
   Only when the screen is at least 900px wide AND 560px tall. Smaller screens fall back to normal page flow (nothing is clipped). */
@media (min-width:900px) and (min-height:560px){
  [data-testid="stMain"]{overflow:hidden;}
  [class*="st-key-rr_pane_"]{height:calc(100vh - 96px) !important;max-height:calc(100vh - 96px) !important;}
}
@media (max-width:900px){
  [data-testid="stHorizontalBlock"]{flex-wrap:wrap;}
}
'''


def single_style_block(css):
    """ONE <style> block with no blank lines. Streamlit renders st.markdown() through Markdown: a blank line, or a second <style> tag
    glued onto the first, ends the HTML block and the rest of the CSS is printed on the page as text. Always inject CSS through this."""
    body = re.sub(r'</?style[^>]*>', '', css)
    return '<style>\n' + '\n'.join(line for line in body.splitlines() if line.strip()) + '\n</style>'


def inject_css(css):
    st.markdown(single_style_block(css), unsafe_allow_html=True)


def inject_theme():
    inject_css(root_css() + GLOBAL_CSS)


def pill(text, kind=''):
    from html import escape
    return f'<span class="rr-pill {kind}">{escape(str(text))}</span>'


def clock(t):
    """'3:42 PM' in the viewer's local time. Accepts an ISO string or a datetime; '—' when missing."""
    if not t:
        return '—'
    if isinstance(t, str):
        t = datetime.fromisoformat(t)
    t = t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t
    return t.astimezone().strftime('%I:%M %p').lstrip('0')
