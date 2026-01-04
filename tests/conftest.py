"""Pytest configuration for test suite."""
import sys
from pathlib import Path

# Add agent-sdk-client to Python path for imports
SDK_CLIENT_DIR = Path(__file__).parent.parent / 'agent-sdk-client'
if str(SDK_CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(SDK_CLIENT_DIR))
