"""Writable output paths for source and installed copies of VoltScope."""
import os
from pathlib import Path
import sys


def output_directory():
    if sys.platform == 'win32' and getattr(sys, 'frozen', False):
        local = os.environ.get('LOCALAPPDATA')
        base = Path(local) if local else Path.home() / 'AppData' / 'Local'
        return base / 'VoltScope' / 'outputs'
    return Path(__file__).resolve().parent / 'outputs'
