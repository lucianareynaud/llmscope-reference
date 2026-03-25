"""Application settings and configuration."""
import os
from pathlib import Path

# Base paths
BASE_DIR = Path(__file__).parent.parent
ARTIFACTS_DIR = BASE_DIR / "artifacts" / "logs"

# Artifact paths - configurable via environment variables
TELEMETRY_PATH = os.getenv(
    "TELEMETRY_PATH",
    str(ARTIFACTS_DIR / "telemetry.jsonl")
)

DECISIONS_PATH = os.getenv(
    "DECISIONS_PATH",
    str(ARTIFACTS_DIR / "policy_decisions.jsonl")
)
