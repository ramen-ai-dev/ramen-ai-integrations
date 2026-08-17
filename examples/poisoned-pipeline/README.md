# We built a 94.2%-accurate hiring model whose decisions were dominated by postcode. Here is how we blocked its prediction at runtime.

## API Key

To run this showcase, you must mint a ramen-ai API key. We offer a **Free
Starter Tier** (1,000 evaluations/month, BYOK). Mint your key at:
**[https://ramenai.dev/pricing](https://ramenai.dev/pricing)**

---

## The Business Goal

This synthetic hiring-screening example demonstrates a problem that accuracy-only model validation can miss.

The intended business question is straightforward: should a candidate progress based on job-related evidence?

The dataset contains three features:

- `technical_score`: the candidate's technical assessment result
- `years_experience`: their relevant professional experience
- `postcode`: a binary location indicator

Technical score and experience are legitimate signals for this simulated decision. Postcode is the proxy-prone feature: it describes where someone lives rather than whether they can perform the job.

## The Accuracy Trap

The training labels are deliberately poisoned. Instead of representing genuine candidate suitability, every training label is copied directly from the postcode field. This simulates a historical selection process in which location determined who progressed.

The validation set contains 120 records. Its labels preserve the same postcode-driven pattern, with seven labels changed to introduce noise. The logistic regression model learns that pattern and correctly reproduces 113 of the 120 validation labels:

**Validation accuracy: 94.2%**

The number is mathematically correct. The interpretation is the problem.

The model is not accurately measuring candidate suitability. It is accurately reproducing a biased historical decision rule. Without feature-level analysis, it could pass an accuracy-only deployment gate.

## The SHAP Reveal

The showcase uses `shap.LinearExplainer` to inspect a proposed inference. The resulting attribution array is:

```text
Feature order:      [technical_score, years_experience, postcode]
SHAP attribution:   [-0.0007,         -0.0680,          3.5031]
```

SHAP measures how each feature contributes to the model output relative to its background expectation.

Technical score contributes almost nothing. Years of experience has a small contribution. Postcode dominates the decision.

This is the distinction between model performance and model behaviour: the validation metric reports whether predictions match the supplied labels, while SHAP helps reveal which features produced those predictions.

## The L2 Boundary

An explanation makes the problem visible, but it does not enforce what happens next.

The showcase wraps the estimator with `RamenGovernedModel` from `ramen-mlflow-guard`. For the governed request, the application supplies both the inference features and the calculated SHAP values to the wrapper.

Before delegating to the inner model's `predict()` method, the wrapper serialises that evidence and evaluates it against the configured proxy-bias policy.

The policy denies the request. `RamenGovernedModel` raises `GovernanceDeniedException`, so the underlying estimator does not execute the governed prediction.

## The Resolution

The unsafe decision does not produce a governed prediction. The application receives remediation steering, relevant statutory anchors and a locally verified Ed25519 receipt bound to the configured policy.

The script verifies two properties before treating the result as a trusted policy interception:

1. The denial includes a locally verified Ed25519 receipt.
2. The receipt resolves to the policy UUID configured by the operator.

The terminal reports:

```text
🚨 [FATAL] INFERENCE HALTED AT L2 BOUNDARY
==================================================
[x] Verdict: BLOCKED
[x] Statute: Directive 2000/78/EC, EU AI Act Annex III
[x] Steering: Remove postcode as a screening criterion to avoid indirect discrimination.
[x] Audit: Receipt Verified (Ed25519)
==================================================
Model execution terminated.
```

This runtime boundary does not replace representative data, fairness testing, model review or human oversight. It adds an enforceable control for cases where unsafe attribution evidence reaches the inference boundary.

The model achieved 94.2% accuracy because it learned the poisoned labels correctly. SHAP exposed the shortcut. The runtime boundary prevented that shortcut from producing a governed prediction.

## Quickstart

On macOS or Linux, from the repository root:

```bash
cd examples/poisoned-pipeline
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and replace the credential placeholders:

```dotenv
RAMEN_API_KEY="ramen_ak_..."
OPENAI_API_KEY="sk-..."
RAMEN_POLICY_UUID="0d5ed2af-5e98-4a8c-92c3-dea26c07bf9a"
```

`OPENAI_API_KEY` is required for self-service BYOK accounts. Remove it when using Enterprise-managed provider credentials.

Run the focused checks and the live showcase:

```bash
./.venv/bin/python -m unittest test_showcase_pipeline.py
./.venv/bin/python showcase_pipeline.py
```

A successful showcase run exits with status `0` after printing the verified `BLOCKED` interception. It exits non-zero if the policy allows the poisoned inference or if the denial cannot be verified against the configured policy.
