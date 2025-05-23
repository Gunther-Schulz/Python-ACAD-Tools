"""Application entry point."""
import sys

# Ensure src directory is in path if running from root, though direct execution of main.py from root
# should generally work if the package structure is standard.
# For robustness if PYTHONPATH isn't set, one might add:
# import os
# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from src.cli.main_cli import run_cli

if __name__ == "__main__":
    run_cli()
