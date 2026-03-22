# Web Adapter

Chunk: **P6-002 Web adapter**

## Scope

Provides a Python adapter API for web surfaces that wraps core Caliper operations:

- request-time assignment,
- render exposure logging,
- click outcome logging,
- conversion outcome logging.

## API

Module: `caliper_adapters.web`

### `WebAdapter`

Construct with:

- `client`: SDK-like client implementing `assign`, `log_exposure`, `log_outcome`
- `workspace_id`
- `job_id`
- optional metric names: `click_metric`, `conversion_metric`

### `assign_request(...)`

- Calls assignment with optional candidate-arm constraints and context.
- Returns lightweight `WebAssignment` (`decision_id`, `arm_id`, `propensity`).
- Keeps assignment separate from exposure so rendering can be tracked only when it actually happens.

### `log_render(...)`

- Records `rendered` exposure for a decision when variant rendering occurs.
- Adds `surface=web` metadata and accepts additional render metadata.

### `log_click(...)`

- Records a single click outcome event (default metric `click`, default value `1.0`).
- Supports custom metric naming for product-specific event taxonomies.

### `log_conversion(...)`

- Records a single conversion outcome event (default metric `conversion`, default value `1.0`).
- Keeps conversion logging distinct from click logging for clearer reporting and reward formulas.

## Validation Coverage

`tests/unit/test_web_adapter.py` verifies:

- assignment wiring with candidate-arm subset support,
- rendered exposure logging on actual render boundaries,
- click and conversion outcomes are logged as distinct metrics.
