-- Views used by the Power BI report (docs/powerbi.md) and checked by tests/test_sql_layer.py.
-- sqrt() is registered from Python by src/bi.py, so this runs on any SQLite build.

-- How many municipalities differ persistently from expected, by verdict.
DROP VIEW IF EXISTS v_verdict_counts;
CREATE VIEW v_verdict_counts AS
SELECT verdict, COUNT(*) AS n_municipalities
FROM fact_effects
GROUP BY verdict;

-- Verdicts per county; Stockholms län is county 01.
DROP VIEW IF EXISTS v_county_summary;
CREATE VIEW v_county_summary AS
SELECT d.county,
       COUNT(*)                                             AS n_municipalities,
       SUM(CASE WHEN e.verdict = 'above' THEN 1 ELSE 0 END) AS n_above,
       SUM(CASE WHEN e.verdict = 'below' THEN 1 ELSE 0 END) AS n_below,
       ROUND(AVG(e.eb_mean), 2)                             AS mean_persistent_effect
FROM dim_municipality AS d
JOIN fact_effects AS e USING (municipality)
GROUP BY d.county;

-- One-year change against the 95 % noise band for the municipality's size
-- (README "Recommendation"): is this year's change more than cohort noise?
-- As in src/descriptives.py, the change is demeaned by the year's average change
-- (removes national shifts) and the band uses this year's cohort.
DROP VIEW IF EXISTS v_change_vs_noise;
CREATE VIEW v_change_vs_noise AS
WITH changes AS (
    SELECT f.municipality,
           f.year,
           f.merit,
           f.cohort_est,
           f.merit - LAG(f.merit) OVER w AS change,
           f.year - LAG(f.year) OVER w   AS gap
    FROM fact_results AS f
    WINDOW w AS (PARTITION BY f.municipality ORDER BY f.year)
),
demeaned AS (
    SELECT *, change - AVG(change) OVER (PARTITION BY year) AS change_dm
    FROM changes
    WHERE change IS NOT NULL AND gap = 1
)
SELECT d.municipality,
       d.year,
       d.merit,
       ROUND(d.change, 1)                                     AS change,
       ROUND(d.change_dm, 1)                                  AS change_vs_national,
       ROUND(1.96 * sqrt(p.a + p.b / d.cohort_est), 1)        AS noise_band_95,
       CASE WHEN ABS(d.change_dm) > 1.96 * sqrt(p.a + p.b / d.cohort_est) THEN 1 ELSE 0 END
                                                              AS outside_band
FROM demeaned AS d
CROSS JOIN param_noise AS p;

-- Municipality card: the latest year next to the three-year average and the persistent
-- effect, which is what the README recommends judging a municipality on.
DROP VIEW IF EXISTS v_municipality_card;
CREATE VIEW v_municipality_card AS
WITH latest AS (SELECT MAX(year) AS year FROM fact_results),
three_year AS (
    SELECT f.municipality, AVG(f.resid) AS resid_3y
    FROM fact_results AS f, latest AS l
    WHERE f.year > l.year - 3
    GROUP BY f.municipality
)
SELECT d.municipality,
       d.name,
       d.county,
       d.stockholm_county,
       ROUND(d.cohort_median, 0) AS cohort_median,
       f.year                    AS latest_year,
       f.merit                   AS merit_latest,
       ROUND(f.expected, 1)      AS expected_latest,
       ROUND(f.resid, 1)         AS resid_latest,
       ROUND(t.resid_3y, 1)      AS resid_3y_avg,
       ROUND(e.eb_mean, 1)       AS persistent_effect,
       ROUND(e.lo95, 1)          AS persistent_lo95,
       ROUND(e.hi95, 1)          AS persistent_hi95,
       e.verdict,
       e.rank_point,
       e.rank_lo,
       e.rank_hi,
       c.change                  AS change_latest,
       c.change_vs_national      AS change_latest_vs_national,
       c.noise_band_95,
       c.outside_band
FROM dim_municipality AS d
JOIN latest AS l
JOIN fact_results AS f ON f.municipality = d.municipality AND f.year = l.year
JOIN three_year AS t ON t.municipality = d.municipality
JOIN fact_effects AS e ON e.municipality = d.municipality
LEFT JOIN v_change_vs_noise AS c ON c.municipality = d.municipality AND c.year = l.year;
