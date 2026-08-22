from __future__ import annotations

from pathlib import Path

POLICY_UUID = "5ae51a4f-46b8-4015-bee7-2c6cc9499561"
DEFAULT_BASE_URL = "https://api.ramenai.dev"
DATASET_ID = "kaggle:nphantawee/pump-sensor-data:v1"
TARGET_NAME = "pump_excursion_within_30_minutes"
SCHEMA_ID = "ramen.mwdta.evidence-envelope.v1"
BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PROFILE_PATH = BASE_DIR / "config" / "evidence-profile.json"
DEFAULT_ARTIFACTS_DIR = BASE_DIR / "artifacts"
