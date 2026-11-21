#!/usr/bin/env python3
"""Launcher: python3 run.py build <inputs.json> --out <dir> | check-env"""
import os
import sys

if sys.version_info < (3, 9):
    sys.stderr.write("finance-soul: нужен Python 3.9 или новее, сейчас %s\n" % sys.version.split()[0])
    sys.exit(2)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from finsoul.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
