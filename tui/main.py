#!/usr/bin/env python3
"""Entry point: `python main.py` from the tui/ directory, or
`python -m app.app` works too - this just gives a friendlier top-level
file to point people at.
"""
from app.app import run

if __name__ == "__main__":
    run()
