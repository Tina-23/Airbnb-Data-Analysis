# Engineering Decision Log
**Project:** Airbnb Market Intelligence — Singapore & Bangkok  
**Candidate:** Christina Ravichandran  
**Assignment:** Expernetic Data Engineer Intern Assessment

---

## Day 1 — Dataset Familiarization, Ingestion & Cleaning (`src/ingest.py`, `src/clean.py`)

### DEC-01 — Use summary `listings.csv` not detailed version
**Decision:** Built pipeline on the summary listings file (18 columns) rather than the detailed version (70+ columns).  
**Reason:** Detailed file was not available at pipeline build time. Summary file contains all columns required for the PRD's mandatory analyses.  
**Trade-off:** Missing `host_is_superhost`, `review_scores_rating`, `amenities` — H2 (superhost test) and property-type normalisation cannot be done.  
**Impact:** Noted in skipped hypotheses section of statistical analysis notebook.

---

### DEC-02 — Drop price nulls rather than impute
**Decision:** Rows where `price` is null are dropped before cleaning.  
**Reason:** Price is the primary analysis metric. Null rates are 28.4% (Singapore) and 19.2% (Bangkok) — imputing at this scale would mean 1 in 4 Singapore prices is synthetic, undermining the validity of every price chart and regression.  
**Alternative considered:** Imputing with neighbourhood median. Rejected because neighbourhood-level medians computed from 70% real data would still propagate uncertainty into 28% of outputs.  
**Final row counts:** Singapore 2,643 (from 3,693), Bangkok 23,273 (from 28,806).

---

### DEC-03 — Use median not mean for price aggregation
**Decision:** All price aggregations (neighbourhood summaries, cross-city comparisons) use median, not mean.  
**Reason:** Price distributions are heavily right-skewed: Singapore skewness = 11.3, Bangkok skewness = 53.2. A listing priced at THB 1,000,000 pulls the mean far from a typical listing's price. Median is robust to these extremes.  
**Applied in:** `enrich.py` neighbourhood aggregates, all EDA charts, SQL queries in `model.py`.

---

### DEC-04 — Cap `maximum_nights` at 365
**Decision:** Any `maximum_nights` value above 365 is capped at 365.  
**Reason:** The calendar file contained a value of 2,147,483,647 (2^31 - 1), which is INT_MAX — a 32-bit integer overflow artifact from the scraper, not a real host constraint. A year (365 days) is the practical maximum for any Airbnb booking window.  
**Rows affected:** 4 Bangkok listings in Nong Chok neighbourhood.

---

### DEC-05 — Fill `reviews_per_month` nulls with 0
**Decision:** Null values in `reviews_per_month` are filled with 0.  
**Reason:** A null here means the listing has never received a review, not that the value is unknown or missing. Filling with 0 is factually correct and enables the column to be used in numerical analysis without dropping rows.  
**Alternative considered:** Dropping null rows. Rejected — these are valid listings, just inactive ones.

---

### DEC-06 — Parse `last_review` to datetime
**Decision:** `last_review` is parsed from string to `datetime64` in `clean.py`.  
**Reason:** As a string, date comparisons are alphabetical not chronological. Datetime type enables subtraction (`days_since_last_review`), groupby-month for seasonality, and proper sort ordering.

---

### DEC-07 — Drop 100% null columns per city
**Decision:** `neighbourhood_group` and `license` are dropped from Bangkok data automatically.  
**Reason:** Both are 100% null in Bangkok — carrying empty columns through the pipeline wastes memory and causes confusion in joins and reports.  
**Singapore retention:** Both columns are kept for Singapore where they contain real data (license field has STR permit types, neighbourhood_group has 5 regions).

---

## Day 2 — Enrichment & Modelling (`src/enrich.py`, `src/model.py`)

### DEC-08 — Left join listings to reviews (not inner)
**Decision:** Listings are left-joined to the review summary.  
**Reason:** An inner join would silently drop all listings with zero reviews — 50% of Singapore and 35% of Bangkok listings. These inactive listings are analytically important (they signal oversupply or poor-quality listings). Left join preserves them with NaN in review-derived columns.

---

### DEC-09 — Occupancy proxy methodology
**Decision:** Estimated occupancy = `(365 - availability_365) / 365`.  
**Reason:** Inside Airbnb's standard methodology. We do not have actual booking data. Availability represents days the host has made the listing bookable — days not available are treated as either booked or blocked by the host.  
**Limitation:** Hosts can block calendar for personal use, renovation, or other reasons that are not bookings. This metric may overestimate occupancy for some listings.

---

### DEC-10 — Calendar inner-joined to listings; listing-level price is the sole price source
**Decision:** `price` and `adjusted_price` from `calendar.csv.gz` are dropped (100% null). The calendar is inner-joined with cleaned listings on `listing_id = id` to attach `room_type` and `neighbourhood` onto every calendar row. The listing's base price is also attached for reference, but the calendar is used exclusively for its `available` (t/f) column — not for per-day pricing.  
**Reason:** Per-day pricing is unavailable. The calendar's `available` column is fully populated and enables H5 to be tested as a weekend vs weekday availability comparison — lower availability on weekends signals higher weekend demand.  
**Impact:** H5 tested via two-proportions z-test on availability rates. Enriched calendar saved to `calendar_{city}_enriched.parquet`. See `enrich.py` `enrich_calendar()`.

---

### DEC-11 — DuckDB for analytical layer
**Decision:** DuckDB used for star schema and SQL queries rather than PostgreSQL or SQLite.  
**Reason:** Zero configuration — no server to install or manage. Reads `.parquet` files natively. Full SQL support including window functions and MEDIAN(). Ideal for a self-contained, reproducible analytical pipeline.

---

### DEC-12 — Parquet for processed data storage
**Decision:** All cleaned and enriched outputs saved as `.parquet` files.  
**Reason:** Parquet is columnar — reads only the columns needed, not the full file. Preserves exact dtypes including `datetime64` (CSV would lose this on re-read). Significantly faster than CSV for the Bangkok dataset (23k rows x 29 columns).

---

### DEC-13 — Convert prices to USD for cross-city comparison
**Decision:** A `price_usd` column is derived in `enrich.py` alongside the local currency `price` column.  
**Reason:** Singapore prices are in SGD and Bangkok prices are in THB. Placing them side by side without conversion is misleading — SGD 221 and THB 1,379 appear numerically close but represent USD 166 vs USD 39 respectively.  
**Exchange rates used:** As of scrape date Sep 2025 — 1 SGD = 0.75 USD, 1 THB = 0.028 USD (xe.com historical rates).  
**What is preserved:** The original `price` column in local currency is kept on every row for within-city analysis. `price_usd` is used only for cross-city comparisons.  
**Limitation:** Exchange rates fluctuate and do not reflect purchasing power parity (PPP).

---

## Day 3 — Statistical Analysis (`notebooks/04_statistical_analysis.ipynb`)

### DEC-14 — Use Mann-Whitney U not t-test for H1
**Decision:** Mann-Whitney U test used for entire-home vs private-room price comparison.  
**Reason:** The t-test assumes normality. Price is highly skewed (skewness > 10 for both cities). Mann-Whitney U is non-parametric and makes no distributional assumptions — appropriate for this data.

---

### DEC-15 — Use log(price) in OLS regression and enhance model features
**Decision:** Dependent variable in OLS regression is `log(price + 1)`, not raw price. Model enhanced beyond the baseline four features.  
**Reason:** Raw price is right-skewed, violating OLS assumptions of normally distributed residuals. Log transformation makes the distribution more symmetric and coefficients interpretable as approximate percentage changes.  
**Enhanced features added:** `reviews_per_month` (demand velocity), `calculated_host_listings_count` (host scale effect), `log(nb_median_price)` (neighbourhood price context). Singapore model also includes neighbourhood fixed effects (ANOVA confirmed location significance, p < 0.001).  
**Outcome:** Singapore R² improved from 0.432 to 0.512. Bangkok R² improved from 0.082 to 0.178.
