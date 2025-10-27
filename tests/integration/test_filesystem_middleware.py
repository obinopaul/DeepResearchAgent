"""Re-export filesystem integration tests so pytest picks them up."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

if sys.version_info >= (3, 14):
    pytest.skip("Requires langchain_anthropic support for Python < 3.14", allow_module_level=True)

pytestmark = []

from agents.deep_agents.tests.integration_tests.test_filesystem_middleware import *  # noqa: F401,F403
