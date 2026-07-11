---
type: security
severity: medium
created: 2026-07-11
source: background-commit-security-review
files: [scripts/templates/experiment.py.tmpl, scripts/scaffold_experiment.py]
---

# Code injection via unescaped config values in experiment.py.tmpl

`scaffold_experiment.py` renders `experiment.py.tmpl` with
`string.Template(...).safe_substitute` (no escaping). The template places
values inside Python string literals:

    SLUG = "$slug"          # <- config.competition_slug
    CV_SCHEME = "$cv_scheme" # <- config.cv.scheme

`slug` and `cv_scheme` come from `control/config.json`. `competition_slug` can
originate from Kaggle competition metadata (untrusted per the Phase 2 threat
model). A value containing `"` + code breaks out of the literal and injects
arbitrary Python into the generated experiment — subverting the phase's
machine-verified-result guarantee.

Safe fields (no action): `metric_name` (validated `in REGISTRY`), `exp_id`,
`exp_dir` (internally generated), `registry_entry` (trusted `repr()`).

## Fix
Render the string fields as Python literals via `repr()`, mirroring
`registry_entry`. In the template change:

    SLUG = $slug
    EXP_ID = $exp_id
    CV_SCHEME = $cv_scheme
    METRIC_NAME = $metric_name
    ap.add_argument("--exp-dir", default=$exp_dir, ...)

and in `scaffold_experiment.py` pass `repr(slug)`, `repr(exp_id)`,
`repr(cv_scheme)`, `repr(metric_name)`, `repr(exp_dir_rel)` in the mapping.
Add a test: a `competition_slug` / `cv_scheme` containing `"` and a code
payload must render as an inert string literal (no execution), and the
generated file must still import/parse.
