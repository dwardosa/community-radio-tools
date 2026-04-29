"""
Shared pytest configuration.

Adds src/ to sys.path so all source modules can be imported without
installing the package. This mirrors how run.py bootstraps the path.
"""
import sys
from pathlib import Path

# Make every test file able to do: from tracker.state import StateTracker
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
