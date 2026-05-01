"""
Entry point. Run from the project root:
    python run.py

Adds src/ to sys.path so package imports resolve correctly.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from main import main  # noqa: E402

if __name__ == "__main__":
    main()
