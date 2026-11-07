"""MAIN-APP UI — opening role-selection screen (colours from ui/theme.py).  Owner: main BREADY app (Feature 1 / shell).  NOT part of any feature package.

Pure presentation: it draws the title + two role cards and calls `on_pick(role)` when a button is pressed. It holds no business
logic, reads no database and imports nothing from `features/`. roles.py owns the role state and calls render_role_picker().

WHERE TO EDIT (everything visual is in the TOKENS and CSS blocks below):
    Title text / size ........ TITLE, and `.rr-title` in CSS
    Card look ................ `.st-key-rr_card_*` in CSS  (border, radius, padding, background)
    Button look .............. `.st-key-rr_btn_*` in CSS  (height, font size, colour)
    Spacing / alignment ...... --rr-gap, --rr-card-pad, `.rr-title` margins
    Tablet / small screens ... the two @media blocks at the bottom of CSS
    Colours .................. the :root TOKENS (light) and the dark-mode override right under them
"""
import streamlit as st

from ui.theme import inject_css, root_css

BRAND = 'BREADY'   # the product name, shown in capitals everywhere
TITLE = BRAND

# ====================================================================
# TOKENS + CSS  (injected only while the landing screen is showing)
# ====================================================================
CSS = '''<style>
/* ---- TOKENS: colours come from the shared design system (ui/theme.py). Only landing-specific sizes live here ---- */
:root{
  --rr-gap:2rem;              /* space between the two cards */
  --rr-card-pad:3.5rem 2rem;  /* inside each card: top/bottom  left/right */
  --rr-landing-radius:22px;
  --rr-landing-btn-h:5rem;    /* touch-friendly button height */
}

/* ---- PAGE: neutral background, content centred with a tablet-friendly max width ---- */
[data-testid="stAppViewContainer"],[data-testid="stApp"]{background:var(--rr-bg);}
div.block-container{max-width:980px !important;padding-top:7vh !important;}

/* ---- Landing only: hide the settings sidebar (it returns as soon as a role is chosen) ---- */
[data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],[data-testid="stExpandSidebarButton"]{display:none;}

/* ---- TITLE: large, bold, centred ---- */
h1.rr-title{   /* h1 + !important: Streamlit's own heading styles would otherwise win */
  text-align:center;color:var(--rr-text) !important;
  font-family:var(--rr-font-family) !important;   /* Lexend */
  font-size:clamp(3.4rem,9vw,6.5rem) !important;   /* scales with screen width */
  font-weight:800 !important;letter-spacing:0.02em;line-height:1.05 !important;
  margin:0 0 clamp(2rem,6vh,4rem) !important;padding:0 !important;
}

/* ---- ROLE CARDS: equal size, one subtle border ---- */
.st-key-rr_card_kitchen,.st-key-rr_card_server{
  background:var(--rr-panel);border:1px solid var(--rr-line);border-radius:var(--rr-landing-radius);
  padding:var(--rr-card-pad);display:flex;flex-direction:column;align-items:stretch;gap:2.2rem;
}
.rr-card-title{
  text-align:center;color:var(--rr-text);margin:0;
  font-family:var(--rr-font-family);
  font-size:1.6rem;font-weight:700;letter-spacing:0.08em;
}

/* ---- BUTTONS: large, high contrast, visible keyboard focus ---- */
.st-key-rr_btn_kitchen button,.st-key-rr_btn_server button{
  min-height:var(--rr-landing-btn-h);width:100%;border-radius:14px;border:0;
  background:var(--rr-accent);color:#fff;
}
.st-key-rr_btn_kitchen button p,.st-key-rr_btn_server button p{font-size:1.45rem;font-weight:700;color:#fff;}
.st-key-rr_btn_kitchen button:hover,.st-key-rr_btn_server button:hover{background:var(--rr-accent-hover);color:#fff;}
.st-key-rr_btn_kitchen button:focus-visible,.st-key-rr_btn_server button:focus-visible{outline:3px solid var(--rr-text);outline-offset:3px;}

/* ---- RESPONSIVE: tablet portrait / phones stack the cards ---- */
@media (max-width:900px){
  :root{--rr-card-pad:2.5rem 1.5rem;--rr-landing-btn-h:4.5rem;}
  div.block-container{padding-top:4vh !important;}
}
@media (max-width:640px){
  [data-testid="stHorizontalBlock"]{flex-wrap:wrap;}
  [data-testid="stColumn"]{min-width:100% !important;}
}
</style>'''


def render_role_picker(roles, on_pick):
    """roles: ordered {role_key: {'title': str, 'button': str}}  (key order = left to right).  on_pick(role_key) is a button callback."""
    inject_css(root_css() + CSS)   # ONE style block (see single_style_block: two glued <style> tags print CSS as text)
    st.markdown(f'<h1 class="rr-title">{TITLE}</h1>', unsafe_allow_html=True)
    cols = st.columns(len(roles), gap='large')  # equal widths; CSS above stacks them on narrow screens
    for col, (role, spec) in zip(cols, roles.items()):
        with col:
            with st.container(key=f'rr_card_{role}'):
                st.markdown(f'<p class="rr-card-title">{spec["title"]}</p>', unsafe_allow_html=True)
                st.button(spec['button'], key=f'rr_btn_{role}', use_container_width=True, on_click=on_pick, args=(role,))
