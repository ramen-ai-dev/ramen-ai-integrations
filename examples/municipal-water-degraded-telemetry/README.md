# Municipal Water Degraded-Telemetry Demo

## API Key

To run this showcase, you must mint a ramen-ai API key. We offer a **Free
Starter Tier** (1,000 evaluations/month, BYOK). Mint your key at:
**[https://ramenai.dev/pricing](https://ramenai.dev/pricing)**

## Dataset

This example trains a deterministic XGBoost classifier on the public [Kaggle Pump Sensor Data](https://www.kaggle.com/datasets/nphantawee/pump-sensor-data), computes authentic TreeSHAP values from the runtime input, injects a deterministic sensor freeze, aggregates attribution by physical source, and evaluates the resulting operational authorization against the deployed ramen AI policy.

## Policy

Policy UUID: `5ae51a4f-46b8-4015-bee7-2c6cc9499561`

The example deliberately blocks both the rural and commuter-bridge versions of the contaminated original prediction. Consequence changes the response route, not the trustworthiness of degraded evidence.

## Important boundary

The ramen evaluation API accepts a single `input` string plus policy selection. It does not parse a Municipal Water evidence object or independently recompute SHAP, sensor health, common modes, or fallback exclusion. This example therefore:

1. Calculates and validates a typed evidence envelope locally.
2. Hashes the deterministic canonical representation.
3. Renders verified facts into a stable input string.
4. Calls only `https://api.ramenai.dev` through the official Python SDK.
5. Requires the expected semantic verdict and a verified Schema V5 receipt.
6. Retains the structured envelope beside the exact receipt-bound input.

The local profile is `demo.mwdta.kaggle-pump.xgb-treeshap.dispatch.v1`. It is not registered or verified by the backend.

## Dataset limitations

The Kaggle dataset is public and immediately obtainable, but Kaggle reports its license as **Unknown**. Its sensor names are anonymous, units and topology are not adequately documented, and utility provenance is weak. Do not redistribute it or describe it as field-validated municipal telemetry. The loader treats each original `sensor_*` column as one physical source and maps every engineered descendant back to that source.

SWaT remains the preferred future adapter because the [official testbed](https://www.sutd.edu.sg/itrust/swat/) has explicit water-process semantics, but access is request-mediated. The dataset adapter is intentionally replaceable.

## Model target

The target is `pump_excursion_within_30_minutes`:

- Only rows currently marked `NORMAL` are eligible for scoring.
- A row is positive when the following 30 minutes first enter `BROKEN` or `RECOVERING`.
- `machine_status` and all future observations are excluded from model features.
- Splits are chronological and purged by the prediction horizon.
- Every split must contain both classes; otherwise execution stops and reports insufficient independent transitions.

Features are latest value, one-step lag, five-sample rolling mean, and five-sample rolling standard deviation for up to twelve usable sources. XGBoost uses one thread and a fixed seed. TreeSHAP explains the raw margin with `tree_path_dependent` perturbation. The rendered `model_probability` is the fitted classifier's raw probability for the replay row; it is not presented as calibrated. Attribution also always comes from that fitted model and row.

## Demo-local profile

- Materiality: grouped absolute source share `>= 0.50`.
- Expected cadence: every adjacent timestamp is strictly increasing and exactly 60 seconds after the preceding timestamp; gaps, duplicates, and irregular intervals fail validation.
- Staleness failure: value age `> 120` seconds.
- Freeze failure: at least three consecutive expected intervals.
- Health coverage: 100% of the half-open feature window.
- Corroboration: all-of qualification with explicit sensing, power, communications, calibration, derived-input, and process-artifact independence.

These are demo choices, not universal policy thresholds. Baseline health is measured from the selected replay window. The separately trained fallback's dominant source is measured independently over the same window and must pass its own health gate.

## Setup

Use Python 3.11 or newer.

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Compute the SHA-256 of the exact operator-approved Kaggle CSV:

```bash
shasum -a 256 /absolute/path/to/sensor.csv
```

Set only local values in `.env`:

```dotenv
RAMEN_API_BASE_URL=https://api.ramenai.dev
RAMEN_API_KEY=
PUMP_SENSOR_DATA_PATH=/absolute/path/to/sensor.csv
PUMP_SENSOR_DATA_SHA256=<64-character-sha256-from-shasum>
```

The loader reads the file at `PUMP_SENSOR_DATA_PATH` only when its digest exactly matches `PUMP_SENSOR_DATA_SHA256`. A missing or mismatched digest fails closed rather than accepting an arbitrary shape-compatible CSV. Use an isolated business-tier demo identity. Never paste a credential or dataset contents into source, reports, logs, or chat.

## Offline verification

The unit suite performs no network calls:

```bash
./.venv/bin/python -m unittest discover -s tests -v
```

Inspect the authenticated real dataset, train the primary model, find a naturally material degraded replay, measure baseline health, and print immutable identities:

```bash
./.venv/bin/python -m municipal_water_degraded_telemetry inspect
```

Persist gitignored model manifests, envelopes, and rendered inputs without calling ramen:

```bash
./.venv/bin/python -m municipal_water_degraded_telemetry train
```

The fallback is a separately trained source-excluding bundle with its own model and feature-schema hashes. Training persists `artifacts/models/fallback/exclusion-proof.json`, containing the suspect source's complete descendant list and the fallback feature names; the fallback envelope binds the canonical proof hash and validation rejects any retained descendant.

Both commands fail rather than fabricate a demonstration if the approved dataset checksum, exact cadence, state vocabulary, target balance, measured health gates, or the `>= 0.50` grouped-attribution trigger cannot be established from real data.

## Production evaluation

After setting `RAMEN_API_KEY`, run:

```bash
./.venv/bin/python -m municipal_water_degraded_telemetry run
```

The runner evaluates:

| Scenario | Expected API `allowed` | Local disposition |
|---|---:|---|
| Healthy baseline | `true` | `ALLOW` |
| Degraded rural original | `false` | `BLOCK` |
| Degraded bridge original | `false` | `BLOCK` |
| Missing/untrusted profile evidence | `false` | `REVIEW_REQUIRED` |
| Separately trained source-excluding fallback | `true` | `ALLOW` |

The API exposes a boolean verdict, not a first-class `REVIEW_REQUIRED` enum. The missing-evidence scenario therefore retains `ramen_allowed: false` and `local_governance_disposition: REVIEW_REQUIRED` as separate facts.

A run succeeds only when:

- The observed verdict matches the scenario expectation.
- The required policy UUID resolves exactly once.
- The SDK verifies the returned V5 Ed25519 receipt and exact input hash.
- No receipt signing alert is present.
- Every block includes violations with reasoning and recovery instructions.

Generated data, models, envelopes, rendered input, receipts, and reports stay under the ignored `artifacts/` directory.

## Architecture

- `data_pipeline.py`: checksum-authenticated real-data validation, leakage-resistant target/splits, XGBoost, TreeSHAP, replay selection, measured source health, and fallback training.
- `profile.py`: immutable demo-local profile loading and validation.
- `attribution.py`: physical-source lineage aggregation and materiality arithmetic.
- `health.py`: half-open interval alignment and deterministic freeze/staleness authority.
- `envelope.py`: evidence validation, fallback descendant-exclusion verification, and canonical hash binding.
- `renderer.py`: the sole structured-evidence-to-input serialization boundary.
- `api_client.py`: fail-closed adapter over the official `RamenClient`.
- `scenarios.py`: distinct decision identities and local dispositions.
- `runner.py`: orchestration, artifact retention, production verdict checks, and reporting.

The full envelope remains local. The signed ramen receipt binds the rendered text and its embedded envelope hash; it does not independently attest the underlying telemetry.
