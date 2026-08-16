from __future__ import annotations

import os
import warnings
from pathlib import Path

_default_showwarning = warnings.showwarning


def _suppress_mlflow_type_hint_warning(
    message: Warning,
    category: type[Warning],
    filename: str,
    lineno: int,
    file=None,
    line: str | None = None,
) -> None:
    if issubclass(category, UserWarning) and "Add type hints to the `predict` method" in str(
        message
    ):
        return
    _default_showwarning(message, category, filename, lineno, file=file, line=line)


warnings.showwarning = _suppress_mlflow_type_hint_warning

import numpy as np
import pandas as pd
import shap
from dotenv import load_dotenv
from scipy.optimize import OptimizeWarning
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score

from ramen_mlflow import GovernanceDeniedException, RamenGovernedModel

warnings.showwarning = _default_showwarning
warnings.filterwarnings("ignore", category=OptimizeWarning)

BASE_DIR = Path(__file__).resolve().parent
FEATURE_NAMES = ["technical_score", "years_experience", "postcode"]

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _required_policy_uuid() -> str:
    ramen_api_key = os.environ.get("RAMEN_API_KEY", "").strip()
    provider_key = os.environ.get("OPENAI_API_KEY", "").strip()
    policy_uuid = os.environ.get("RAMEN_POLICY_UUID", "").strip()

    if not ramen_api_key or ramen_api_key == "ramen_ak_...":
        raise RuntimeError("RAMEN_API_KEY is not configured")
    if provider_key == "sk-...":
        raise RuntimeError(
            "Replace OPENAI_API_KEY or remove it when using Enterprise-managed keys"
        )
    if not policy_uuid or policy_uuid == "<YOUR_POLICY_UUID>":
        raise RuntimeError("RAMEN_POLICY_UUID is not configured")
    return policy_uuid


def _verified_policy_alert(
    exc: GovernanceDeniedException,
    policy_uuid: str,
) -> str:
    if not exc.receipt_verified:
        raise ValueError("governance denial did not include a verified receipt")
    if policy_uuid not in exc.policy_ids:
        raise ValueError("governance denial did not resolve the configured policy")

    statutes = ", ".join(exc.statutory_anchors) or "Not provided"
    steering = exc.steering or "Not provided"
    return "\n".join(
        [
            "🚨 [FATAL] INFERENCE HALTED AT L2 BOUNDARY",
            "==================================================",
            "[x] Verdict: BLOCKED",
            f"[x] Statute: {statutes}",
            f"[x] Steering: {steering}",
            "[x] Audit: Receipt Verified (Ed25519)",
            "==================================================",
            "Model execution terminated.",
        ]
    )


def main() -> int:
    load_dotenv(dotenv_path=BASE_DIR / ".env", override=False)
    policy_uuid = _required_policy_uuid()

    rng = np.random.default_rng(2026)
    train_size = 480
    validation_size = 120

    train_postcode = np.tile([0.0, 1.0], train_size // 2)
    rng.shuffle(train_postcode)
    x_train = pd.DataFrame(
        {
            "technical_score": rng.normal(75.0, 10.0, train_size),
            "years_experience": rng.uniform(1.0, 15.0, train_size),
            "postcode": train_postcode,
        }
    )
    y_train = train_postcode.astype(int)

    validation_postcode = np.tile([0.0, 1.0], validation_size // 2)
    rng.shuffle(validation_postcode)
    x_validation = pd.DataFrame(
        {
            "technical_score": rng.normal(75.0, 10.0, validation_size),
            "years_experience": rng.uniform(1.0, 15.0, validation_size),
            "postcode": validation_postcode,
        }
    )
    y_validation = validation_postcode.astype(int)
    y_validation[:7] = 1 - y_validation[:7]

    model = LogisticRegression(max_iter=1000).fit(x_train, y_train)
    validation_accuracy = accuracy_score(
        y_validation,
        model.predict(x_validation),
    )
    print(
        f"{GREEN}[SYSTEM] Model Trained Successfully. "
        f"Validation Accuracy: {validation_accuracy * 100:.1f}%.{RESET}"
    )

    inference_index = int(np.flatnonzero(validation_postcode == 1.0)[0])
    inference_row = x_validation.loc[[inference_index]]
    background = shap.maskers.Independent(x_train, max_samples=train_size)
    explainer = shap.LinearExplainer(model, background)
    shap_values = explainer(inference_row).values[0]

    print(
        f"{YELLOW}[SYSTEM] Generating SHAP feature attributions for inference..."
        f"{RESET}"
    )
    print(f"{YELLOW}[SHAP] Feature order: {FEATURE_NAMES}{RESET}")
    print(
        f"{YELLOW}[SHAP] Attribution array: "
        f"{np.round(shap_values, 4).tolist()}{RESET}"
    )

    governed_model = RamenGovernedModel(
        policy_ids=[policy_uuid],
        inner_model=model,
        model_name="poisoned-hiring-pipeline",
        feature_names=FEATURE_NAMES,
    )

    try:
        governed_model.predict(
            None,
            inference_row,
            params={"shap_values": [shap_values.tolist()]},
        )
    except GovernanceDeniedException as exc:
        try:
            alert = _verified_policy_alert(exc, policy_uuid)
        except ValueError as verification_error:
            print(
                f"{RED}{BOLD}[FATAL] GOVERNANCE EVALUATION FAILED\n"
                f"{verification_error}\n{exc}{RESET}"
            )
            return 1
        print(f"{RED}{BOLD}{alert}{RESET}")
        return 0

    print(
        f"{RED}{BOLD}[FATAL] Governance boundary allowed poisoned inference.{RESET}"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
