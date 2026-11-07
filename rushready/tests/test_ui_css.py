"""Guards against the 'CSS printed as text' bug: Streamlit renders st.markdown() through Markdown, so injected CSS must be ONE <style>
block with no blank lines. Run: python -m pytest tests/test_ui_css.py -q"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import frontdesk
import landing
import packing
from features.communication import styles
from ui import theme


def assert_safe(block):
    assert block.startswith('<style>') and block.rstrip().endswith('</style>')
    assert len(re.findall(r'<style', block)) == 1 and len(re.findall(r'</style>', block)) == 1, 'exactly one style block'
    assert '\n\n' not in block, 'a blank line would end the HTML block and print the rest as text'


def test_main_ui_css_is_one_clean_style_block():
    assert_safe(theme.single_style_block(theme.root_css() + theme.GLOBAL_CSS))
    assert_safe(theme.single_style_block(theme.root_css() + landing.CSS))      # landing used to glue two <style> tags together
    assert_safe(theme.single_style_block(frontdesk.CSS))
    assert_safe(theme.single_style_block(packing.CSS))


def test_feature3_css_is_already_safe():
    assert_safe(styles.CSS)


def test_helper_repairs_messy_input():
    messy = '<style>a{b:c}</style><style>\n\nd{e:f}\n\n</style>'
    assert_safe(theme.single_style_block(messy))
