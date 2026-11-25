-- Star schema for the BI layer (SQLite). Loaded by src/bi.py from data/processed and reports/.
-- One row per municipality in dim_municipality, one per municipality x year in fact_results.

DROP TABLE IF EXISTS dim_municipality;
CREATE TABLE dim_municipality (
    municipality     TEXT PRIMARY KEY,   -- four-digit municipality code, e.g. '0114'
    name             TEXT NOT NULL,
    county           TEXT NOT NULL,      -- two-digit county code
    stockholm_county INTEGER NOT NULL,   -- 1 = Stockholms län
    cohort_median    REAL                -- median estimated grade-9 pupils per year
);

DROP TABLE IF EXISTS dim_year;
CREATE TABLE dim_year (
    year INTEGER PRIMARY KEY             -- spring term
);

DROP TABLE IF EXISTS fact_results;
CREATE TABLE fact_results (
    municipality           TEXT NOT NULL REFERENCES dim_municipality (municipality),
    year                   INTEGER NOT NULL REFERENCES dim_year (year),
    merit                  REAL,         -- average merit value, 17 subjects, school location
    expected               REAL,         -- expected from pupil background (OLS, D10)
    resid                  REAL,         -- merit - expected
    cohort_est             REAL,         -- estimated grade-9 pupils (grades 1-9 / 9)
    parents_post_secondary REAL,         -- % of pupils whose parents have post-secondary education
    foreign_background     REAL,         -- % of pupils with foreign background
    PRIMARY KEY (municipality, year)
);

DROP TABLE IF EXISTS fact_effects;
CREATE TABLE fact_effects (
    municipality    TEXT PRIMARY KEY REFERENCES dim_municipality (municipality),
    eb_mean         REAL,                -- persistent difference from expected (empirical Bayes)
    lo95            REAL,
    hi95            REAL,
    verdict         TEXT CHECK (verdict IN ('above', 'below', 'not distinguishable')),
    rank_point      INTEGER,
    rank_lo         INTEGER,
    rank_hi         INTEGER,
    p_top_decile    REAL,
    p_bottom_decile REAL
);

-- Cohort-noise model from reports/descriptives.json: var(change) = a + b / n.
DROP TABLE IF EXISTS param_noise;
CREATE TABLE param_noise (
    a REAL NOT NULL,
    b REAL NOT NULL
);
