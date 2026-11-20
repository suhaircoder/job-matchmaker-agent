"""Job Matchmaker Agent: fetch listings, rank them, and notify the user."""

import os

# Same bypass as app.py, for the daily runner and tests.
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

__version__ = "1.0.0"
