# How much of the municipal school ranking is noise?

Every year Sweden's 290 municipalities are ranked on how their grade-9 pupils do. This project asks which municipalities do *consistently* better or worse than their pupils' background predicts — and how much of one year's rank is just noise that should not trigger a review.

> **Status: work in progress.** Results, figures and recommendations are added as the analysis is completed. Nothing below is a finding yet.

<!-- Hero figure: map of persistent municipality effects with rank intervals (M8) -->

## Business question
Education committees and school directors react to annual rankings (SKR *Öppna jämförelser*, Skolverket SALSA, local press). **Which municipalities do consistently better or worse in grade 9 than pupil background predicts, and how large must a one-year change be before it is more than noise?**

## Key findings
*To be added (M8), each with an interval.*

## Recommendation
*To be added (M8).*

## Approach
1. Brief and pre-registered analysis plan (`docs/brief.md`, `docs/decisions.md`).
2. Data quality: coverage, suppression, breaks, reconciliation (`docs/data_quality.md`).
3. Expected merit value from pupil background (regression with diagnostics).
4. Split of residual variation into a persistent municipality part and year-to-year noise (mixed model, reliability, shrinkage, rank intervals).
5. Maps, spatial autocorrelation and a Stockholm-county view.
6. Robustness checks and QA.

## Data
- **Kolada** (RKA) — municipality-level school statistics from Skolverket and SCB, open API, no key.
- **SCB open geodata (DeSO)** — dissolved to municipality boundaries, CC0.

All data is real. Nothing is simulated except where explicitly labelled (e.g. rank intervals are model-based simulations).

## How to run
Python 3.12.

**macOS/Linux**
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m pytest
python scripts/run_pipeline.py probe
```

**Windows (PowerShell)**
```powershell
py -3.12 -m venv .venv; .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pytest
python scripts/run_pipeline.py probe
```

## Project structure
```
data/raw/          downloaded data and probe output
data/processed/    analysis dataset
docs/              brief, decisions, data quality, QA
reports/           results (JSON) and figures
scripts/           pipeline entry point
src/               Kolada client, municipality codes, geodata helpers, analysis
tests/             pytest
```

## Limitations
*To be completed.* The model removes only measured background; residuals are not "value added".

## Technology
Python (pandas, statsmodels, geopandas, libpysal/esda, matplotlib), pytest, GitHub Actions.

## License
MIT (code). Data: see the sources above for their terms.
