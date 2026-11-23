# Brief (written before any outcome data was fetched)

## Business question
Every year, each of Sweden's 290 municipalities sees its grade-9 results compared with all the others — in SKR's *Öppna jämförelser – Grundskola*, Skolverket's SALSA model values and local newspaper rankings. Education committees (utbildningsnämnder) and school directors react to these lists: they commission reviews when the rank drops and claim success when it rises.

**Which municipalities do consistently better or worse in grade 9 than their pupils' background predicts, and how much of a single year's rank is noise that a committee should not react to?**

Decision supported: whether a municipality's position justifies action (review, resources, copying a peer's practice), and which peers are fair to compare with.

## Measure (primary)
- **Outcome:** average merit value (genomsnittligt meritvärde, 17 subjects) of pupils leaving grade 9 in the spring term.
- **Unit:** municipality × spring term. **Population:** pupils registered in the municipality (*hemkommun*), all school providers — the municipality is responsible for its residents' schooling whether the school is municipal or independent. Municipal schools only is a robustness check. *Amended in Run 1 (before outcome data): outcome and background must refer to the same pupils — see D1; if background exists only by school location, the primary population is pupils in schools located in the municipality (lägeskommun).*
- **Window:** spring terms 2015–2025 (narrowed in M2 if the probe shows breaks).
- **Expected value:** from a model of the outcome on pupil background (parents' education, newly arrived pupils, share of boys and similar) measured for the same pupils. The exact covariates are frozen in `decisions.md` in M2 from what the probe shows is available — before any residual or rank is computed.
- **"Better than expected":** a municipality's persistent component (random intercept across years), not one year's residual.

## Done means
1. An expected value per municipality-year with documented model diagnostics.
2. A split of the variation in residuals into a persistent municipality part and a year-to-year part (reliability), with intervals.
3. Rank intervals per municipality and the number that can be told apart from the national average.
4. A concrete rule a committee can use: how large a one-year change has to be before it is more than noise, by municipality size.
5. A map and a Stockholm-county view, with a check for spatial clustering of residuals.

## Results that would NOT answer the question
- A raw ranking of merit values (that is mainly a ranking of pupil background).
- One year's residual ranking without uncertainty.
- Calling a residual a "school quality effect" or "value added": the model only removes measured background. Unmeasured differences (e.g. selection into the municipality, grading practice) remain in the residual.

## Must not change silently
Outcome, population (hemkommun), window, the covariate set, and the definition of "consistently better". Any change after results are seen is logged separately in `decisions.md`.

## Sub-questions and sources
| # | Sub-question | Source | Verified? |
|---|---|---|---|
| 1 | Merit value per municipality and year | Kolada (from Skolverket) | Probe M1 |
| 2 | Pupil background per municipality and year | Kolada / Skolverket | Probe M1 |
| 3 | Cohort size (for noise) | Kolada | Probe M1 |
| 4 | Published model values to reconcile against (SALSA/SKR) | Kolada | Probe M1 |
| 5 | Municipality boundaries | SCB open geodata (DeSO, CC0) | Probe M1 |
