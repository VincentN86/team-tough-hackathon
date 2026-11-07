"""Launch the integrated BREADY team app from the repository root."""
from pathlib import Path
import runpy
import sys

APP_DIR = Path(__file__).resolve().parent / 'rushready'
sys.path.insert(0, str(APP_DIR))
runpy.run_path(str(APP_DIR / 'app.py'), run_name='__main__')
