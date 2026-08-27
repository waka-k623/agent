from __future__ import annotations

import sys
from pathlib import Path

# Render currently starts `streamlit run app/dashboard.py` directly.
# Ensure the repository root is importable, then hand off to the unified Master UI.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.master_dashboard import *  # noqa: F401,F403,E402
