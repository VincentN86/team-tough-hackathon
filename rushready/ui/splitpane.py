"""MAIN-APP UI — draggable divider between two side-by-side panes.  Owner: main BREDDY UI (shell). Not a feature.

Streamlit has no resizable columns, so this is a tiny zero-height custom component (ui/splitter/index.html). Call
`render_splitter('rr_pane_queue', 'rr_pane_voice')` right AFTER the two `st.columns` panes were drawn inside keyed containers
(`st.container(key='rr_pane_queue')` ...). It overlays a real divider (mouse / touch / pen drag, arrow keys, double-click to reset) and
resizes the two columns live in the browser — nothing is sent to Python, so dragging never reruns the app or disturbs widgets/state.

Limits: 340px minimum for the left pane, 300px for the right (see index.html). Below 900px wide the panes stack and the divider hides.
The chosen ratio is saved in the browser (localStorage 'breddy_split_ratio').
"""
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

_splitter = components.declare_component('breddy_splitter', path=str(Path(__file__).parent / 'splitter'))


def render_splitter(left_key, right_key, default=0.6, min_left=340, min_right=300):
    """left_key / right_key: the `key=` of the two pane containers (without the 'st-key-' prefix)."""
    with st.container(key='rr_split_host'):   # zero-height host (CSS in theme.py) so the component adds no layout space
        _splitter(left=left_key, right=right_key, default=default, minLeft=min_left, minRight=min_right, key=f'splitter_{left_key}_{right_key}')
