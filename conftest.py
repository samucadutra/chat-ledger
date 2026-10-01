"""Root pytest configuration shared by every Python test package.

Loads ``.env.test`` into the process environment *before* any test module
imports application code, without overriding variables already exported
(CI or a developer can point ``TEST_DATABASE_URL`` elsewhere).
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent

for _key, _value in dotenv_values(ROOT / ".env.test").items():
    if _value is not None:
        os.environ.setdefault(_key, _value)
