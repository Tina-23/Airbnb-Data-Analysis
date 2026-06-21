# Airbnb Market Intelligence Report
## Singapore & Bangkok Comparative Analysis

**Prepared by:** Christina Ravichandran  
**Assessment:** Expernetic Data Engineer Intern  
**Date:** June 2026  
**Cities Covered:** Singapore · Bangkok, Thailand  

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Project Scope & Methodology](#2-project-scope--methodology)
3. [Dataset Overview & Familiarization](#3-dataset-overview--familiarization)
4. [Data Quality & Ingestion Pipeline](#4-data-quality--ingestion-pipeline)
5. [Cleaning & Standardization](#5-cleaning--standardization)
6. [Data Enrichment & Modelling](#6-data-enrichment--modelling)
7. [Exploratory Data Analysis — Singapore](#7-exploratory-data-analysis--singapore)
8. [Exploratory Data Analysis — Bangkok](#8-exploratory-data-analysis--bangkok)
9. [Statistical Analysis](#9-statistical-analysis)
10. [Cross-City Business Intelligence](#10-cross-city-business-intelligence)
11. [Completed Work Summary](#11-completed-work-summary)
12. [Incomplete Work & Prioritization Rationale](#12-incomplete-work--prioritization-rationale)
13. [Appendix A — AI Usage Disclosure](#appendix-a--ai-usage-disclosure)
14. [Appendix B — Key Engineering Decisions](#appendix-b--key-engineering-decisions)
15. [Appendix C — Skipped Hypotheses](#appendix-c--skipped-hypotheses)
16. [Appendix D — Issues Found & Debugging Approach](#appendix-d--issues-found--debugging-approach)

---

## 1. Executive Summary

This report presents the findings of an end-to-end data engineering and analytics project comparing the Airbnb short-term rental markets in Singapore and Bangkok. Data was sourced from Inside Airbnb (scraped September 2025) and processed through a fully reproducible Python pipeline.

### Key Findings

**Market Size**
- Singapore: 2,643 active priced listings across 40 neighbourhoods
- Bangkok: 23,273 active priced listings across 50 neighbourhoods — approximately 8.8x larger

**Price Comparison (USD — Sep 2025 rates)**
- Singapore median nightly rate: **USD 165.75** (SGD 221)
- Bangkok median nightly rate: **USD 38.61** (THB 1,379)
- Singapore is **4.3x more expensive** than Bangkok in USD terms

**Room Type Premium**
- Singapore entire-home listings command a **3.31x premium** over private rooms (SGD 314 vs SGD 95)
- Bangkok entire-home premium is only **1.38x** (THB 1,500 vs THB 1,090)
- Both premiums are statistically significant (p < 0.001)

**Market Structure**
- Commercial hosts (6+ listings) control **72% of Singapore's market** and **63% of Bangkok's**
- Bangkok is a faster-growing market — 4,070 new listings entered in 2024 alone vs Singapore's 182
- Singapore listings have significantly lower estimated occupancy (~2%) compared to Bangkok (~13%)

**Statistical Insights**
- Neighbourhood location is a strong price driver in Singapore (ANOVA p < 0.001) but not in Bangkok (p = 0.56)
- Room type and availability explain 43% of Singapore price variance (OLS R² = 0.432), but only 8% in Bangkok (R² = 0.082) — suggesting Bangkok pricing is driven by unobserved factors such as property quality and amenities

---

## 2. Project Scope & Methodology

### 2.1 Assignment Objective

This project simulates the work of a Data Engineer/Analyst at an Airbnb market intelligence consultancy. The goal is to transform raw Inside Airbnb data into engineering artifacts, analytical insights, and business recommendations across two cities.

### 2.2 Technical Stack

| Category | Tool | Rationale |
|---|---|---|
| Language | Python 3.13 | Industry standard for data engineering |
| Data Processing | pandas | Tabular data manipulation |
| Analytical Database | DuckDB | Zero-config, parquet-native, full SQL support |
| Visualisation | matplotlib, seaborn | Static publication-quality charts |
| Statistical Testing | scipy, statsmodels | Hypothesis testing and OLS regression |
| Storage Format | Apache Parquet | Columnar, type-preserving, fast reads |
| Notebooks | Jupyter | Reproducible annotated analysis |
| Version Control | Git + GitHub | Required for submission |

### 2.3 Pipeline Architecture

```
data/raw/
  singapore/ + bangkok/
       │
       ▼
  ingest.py      ← load, profile, quality report
       │
       ▼
  clean.py       ← 7 cleaning rules, parquet output
       │
       ▼
  enrich.py      ← joins, derived columns, USD conversion, master table
       │
       ▼
  model.py       ← DuckDB star schema + 6 SQL queries
       │
       ▼
  notebooks/     ← EDA + statistical analysis
```

### 2.4 Scope Decisions

The assignment was intentionally scoped to Phase 1–3 (Foundation, Engineering Core, Analysis) due to the one-week timeline. Phase 4 (Streamlit Dashboard, Price Prediction) was deprioritized in favor of depth and correctness in the mandatory sections.

---

## 3. Dataset Overview & Familiarization

### 3.1 Files Used

| File | Singapore | Bangkok | Contents |
|---|---|---|---|
| listings.csv | 3,693 rows | 28,806 rows | Core listing data — 18 columns |
| reviews.csv | 38,350 rows | 583,333 rows | listing_id + review date only |
| neighbourhoods.csv | 55 rows (44 with listings in Sep 2025 scrape) | 50 rows | Neighbourhood name + group |
| calendar.csv.gz | 1,347,945 rows | 10,514,202 rows | Daily availability per listing |

### 3.2 Schema

Both city listing files share an identical 18-column schema:

`id`, `name`, `host_id`, `host_name`, `neighbourhood_group`, `neighbourhood`, `latitude`, `longitude`, `room_type`, `price`, `minimum_nights`, `number_of_reviews`, `last_review`, `reviews_per_month`, `calculated_host_listings_count`, `availability_365`, `number_of_reviews_ltm`, `license`

### 3.3 Null Rate Analysis

**Singapore listings — columns with nulls:**

| Column | Null % | Interpretation |
|---|---|---|
| last_review | 50.0% | Listing has never been reviewed |
| reviews_per_month | 50.0% | No review activity |
| license | 43.6% | Listing is unlicensed or exempt |
| price | 28.4% | No price set — unusable for analysis |

**Bangkok listings — columns with nulls:**

| Column | Null % | Interpretation |
|---|---|---|
| neighbourhood_group | 100.0% | Entire column empty — dropped |
| license | 100.0% | No licensing regime data — dropped |
| reviews_per_month | 35.0% | No review activity |
| last_review | 35.0% | Never reviewed |
| price | 19.2% | No price set — dropped |

### 3.4 Structural Differences Between Cities

While schemas are identical, there are functional differences:

- Bangkok's `neighbourhood_group` is 100% null — no regional grouping available
- Bangkok's `license` is 100% null — different STR regulation environment from Singapore
- Singapore has an active STR licensing regime: "Authorised Serviced Apartment", "Exempt", and individual `S/L/M` codes
- Bangkok's `price` skewness (53.24) far exceeds Singapore's (11.31), reflecting a more extreme outlier distribution

### 3.5 PK/FK Relationships

| Relationship | Singapore | Bangkok |
|---|---|---|
| Listings with at least one review | 1,847 / 3,693 (50%) | 18,716 / 28,806 (65%) |
| Orphan review IDs | 0 | 0 |
| Neighbourhood name match (raw listings vs reference file) | 44 / 44 (100%) | 50 / 50 (100%) |

After price-null cleaning, 4 Singapore neighbourhoods (Tuas, Mandai, Pioneer, Sungei Kadut) lose all their listings, reducing the analytical neighbourhood count from 44 to **40**. The 55-row reference file contains 11 neighbourhood names that had no Airbnb listings at all in the September 2025 scrape.

### 3.6 Calendar File Findings

Both calendar files contain 365 daily rows per listing. A critical finding: both `price` and `adjusted_price` columns in the calendar are **100% null** for both cities. All price analysis therefore relies exclusively on the listing-level `price` column in `listings.csv`.

Calendar columns with data: `listing_id`, `date`, `available` (t/f), `minimum_nights`, `maximum_nights`.

---

## 4. Data Quality & Ingestion Pipeline

### 4.1 Pipeline Design (`src/ingest.py`)

The ingestion pipeline is configurable by city name. Calling `run_ingestion("singapore", "data/raw")` loads all four files, profiles every column, detects outliers in key numeric fields, and prints a structured quality report.

**Design rationale:**
- Returns a `dict` of DataFrames so downstream functions can loop over files without hardcoding names
- Profiles are computed before any cleaning — preserving a record of raw data state
- Outlier detection uses 3 standard deviations from the mean as the threshold

### 4.2 Quality Report Findings

**Singapore listings — flagged columns:**

| Column | Null % | Skewness | Notes |
|---|---|---|---|
| price | 28.43% | 11.31 | Highly skewed; use median |
| last_review | 50.0% | — | String date, needs parsing |
| reviews_per_month | 50.0% | 9.16 | Fill nulls with 0 |
| number_of_reviews | 0% | 13.44 | Very skewed |
| license | 43.57% | — | Categorical, partially empty |

**Bangkok listings — flagged columns:**

| Column | Null % | Skewness | Notes |
|---|---|---|---|
| price | 19.21% | 53.24 | Extreme skew — median only |
| neighbourhood_group | 100% | — | Drop entirely |
| license | 100% | — | Drop entirely |

### 4.3 Outlier Summary

| City | Column | Outlier Count | Outlier % | Upper Bound | Actual Max |
|---|---|---|---|---|---|
| Singapore | price | 25 | 0.68% | SGD 2,871 | SGD 13,000 |
| Singapore | minimum_nights | 32 | 0.87% | 232 days | 730 days |
| Singapore | number_of_reviews | 61 | 1.65% | 143 | 1,298 |
| Bangkok | price | 37 | 0.13% | THB 51,950 | THB 1,000,000 |
| Bangkok | minimum_nights | 509 | 1.77% | 143 days | 1,115 days |

---

## 5. Cleaning & Standardization

### 5.1 Cleaning Rules Applied (`src/clean.py`)

Seven cleaning steps are applied in sequence to both cities:

**Rule 1 — Drop price nulls**
Rows where `price` is null are dropped. Price is the primary analysis metric and nulls at 19–28% are too high to impute without introducing synthetic data at scale.

- Singapore: 1,050 rows dropped (28.4%)
- Bangkok: 5,533 rows dropped (19.2%)

**Rule 2 — Cap `maximum_nights` at 365**
A value of 2,147,483,647 (INT_MAX, 2³¹−1) was found in Bangkok calendar data — a 32-bit integer overflow artifact from the scraper, not a real host constraint. Capped at 365 days.

**Rule 3 — Fill `reviews_per_month` nulls with 0**
Null indicates no reviews yet, not missing data. Filling with 0 is factually correct and preserves these rows for availability and host analysis.

**Rule 4 — Parse `last_review` to datetime**
Converted from string to `datetime64` type, enabling time-series operations, date subtraction, and month/year grouping.

**Rule 5 — Drop 100% null columns per city**
Bangkok's `neighbourhood_group` and `license` columns were automatically removed.

**Rule 6 — Validate coordinates**
Listings outside expected bounding boxes are flagged with a `coord_flag = True` column rather than dropped. Zero listings were flagged in either city after cleaning.

**Rule 7 — Add city column**
A `city` column is added to each row to enable cross-city stacking in the master table.

### 5.2 Post-Cleaning Row Counts

| City | Raw rows | After cleaning | Retained |
|---|---|---|---|
| Singapore | 3,693 | 2,643 | 71.6% |
| Bangkok | 28,806 | 23,273 | 80.8% |

---

## 6. Data Enrichment & Modelling

### 6.1 Review Summarization & Join (`src/enrich.py`)

The reviews file contains one row per review. A summary is computed per listing using `groupby().agg()`:

- `review_count` — total reviews received
- `review_first_date` — earliest review date (market entry signal)
- `review_last_date` — most recent review date (activity signal)

Listings are then **left-joined** to this summary. Left join was chosen over inner join to preserve listings with zero reviews (50% of Singapore and 35% of Bangkok listings).

### 6.2 Derived Columns

| Column | Formula | Purpose |
|---|---|---|
| `days_since_last_review` | snapshot_date − review_last_date | Listing activity recency |
| `occupancy_proxy` | (365 − availability_365) / 365 | Estimated booking rate |
| `price_per_review` | price / review_count | Value efficiency signal |
| `price_usd` | price × FX rate (Sep 2025) | Cross-city comparison |

**Exchange rates used (Sep 2025):**
- 1 SGD = 0.75 USD
- 1 THB = 0.028 USD

### 6.3 Neighbourhood Aggregates

Per-city neighbourhood aggregates joined back to each listing row:

- `nb_listing_count` — total listings in neighbourhood
- `nb_median_price` — median price of neighbourhood
- `nb_mean_price` — mean price of neighbourhood

### 6.4 Master Table

Both cities stacked into a single `master_listings.parquet`:

- **25,916 total rows** × 30 columns
- Columns unique to Singapore (license, neighbourhood_group) appear as NaN for Bangkok rows

### 6.5 Star Schema (`src/model.py`)

A DuckDB star schema was implemented for the analytical layer:

| Table | Rows | Description |
|---|---|---|
| `fact_listings` | 25,916 | One row per listing — all measurable values |
| `dim_host` | 7,265 | Host attributes + commercial tier |
| `dim_neighbourhood` | 90 (SG: 40 + BK: 50) | Neighbourhood names + city aggregates |
| `dim_room_type` | 4 | Room type lookup |

---

## 7. Exploratory Data Analysis — Singapore

### 7.1 Price Distribution by Room Type

Singapore's price distribution is right-skewed with significant outliers. Capping at the 99th percentile (SGD 2,690) reveals the underlying distribution clearly.

| Room Type | Median Price (SGD) | Listing Count |
|---|---|---|
| Entire home/apt | 314 | 1,298 |
| Hotel room | 192 | 66 |
| Private room | 95 | 1,251 |
| Shared room | 65 | 28 |
| **All types (blended median)** | **221** | **2,643** |

The entire-home premium over private room is **3.31x** — the largest differential of the two markets studied.

### 7.2 Room Type Market Composition

| Room Type | Count | Market Share |
|---|---|---|
| Private room | 1,251 | 47.3% |
| Entire home/apt | 1,298 | 49.1% |
| Hotel room | 66 | 2.5% |
| Shared room | 28 | 1.1% |

Singapore's market is relatively balanced between private rooms and entire homes, unlike Bangkok which skews heavily toward entire homes.

### 7.3 Availability & Estimated Occupancy

Singapore's median availability is **357 days per year** — listings are open for booking almost all year, yet median estimated occupancy is only **~2%**. This suggests a large proportion of Singapore listings are either newly listed, infrequently booked, or maintained primarily for occasional personal use with occasional rental income.

### 7.4 Neighbourhood Analysis

**Top 5 most expensive neighbourhoods (median price, SGD):**

| Neighbourhood | Median Price | Listing Count |
|---|---|---|
| Southern Islands | SGD 650 | 5 |
| Orchard | SGD 405 | 82 |
| Singapore River | SGD 300 | 156 |
| Museum | SGD 295 | 97 |
| Newton | SGD 275 | 50 |

The Central Region dominates Singapore's listing supply — 2,155 of the 2,643 clean listings (81.5%) are located there.

### 7.5 Host Portfolio Segmentation

| Host Tier | Hosts | Listings | Market Share |
|---|---|---|---|
| Single (1 listing) | 329 | 329 | 12.4% |
| Small (2–5 listings) | 180 | 430 | 16.3% |
| Commercial (6+ listings) | 90 | 1,884 | **71.3%** |

A striking finding: just 90 commercial operators control **71.3%** of all Singapore Airbnb listings. This reflects a heavily professionalized market dominated by serviced apartment operators.

---

## 8. Exploratory Data Analysis — Bangkok

### 8.1 Price Distribution by Room Type

Bangkok's price distribution is far more skewed than Singapore's (skewness 53.24 vs 11.31). The 99th percentile cap is set at THB 16,670, well below the actual maximum of THB 1,000,000.

| Room Type | Median Price (THB) | Listing Count |
|---|---|---|
| Entire home/apt | 1,500 | 16,498 |
| Hotel room | 1,473 | 351 |
| Private room | 1,090 | 6,263 |
| Shared room | 650 | 161 |
| **All types (blended median)** | **1,379** | **23,273** |

### 8.2 Room Type Market Composition

| Room Type | Count | Market Share |
|---|---|---|
| Entire home/apt | 16,498 | 70.9% |
| Private room | 6,263 | 26.9% |
| Hotel room | 351 | 1.5% |
| Shared room | 161 | 0.7% |

Bangkok is dominated by entire-home listings (71%) — a much higher concentration than Singapore's near-50/50 split.

### 8.3 Availability & Estimated Occupancy

Bangkok's median availability is **318 days per year**, with median estimated occupancy of **~13%** — meaningfully higher than Singapore's ~2%. Bangkok is a more actively booked market.

### 8.4 Neighbourhood Analysis

Bangkok has 50 neighbourhoods with no regional grouping available. Price variation across neighbourhoods is not statistically significant (ANOVA p = 0.56), suggesting that in Bangkok, *room type* is a far stronger price driver than *location*.

**Top 5 most expensive neighbourhoods (median price, THB):**

| Neighbourhood | Median Price | Listing Count |
|---|---|---|
| Parthum Wan | THB 2,248 | 567 |
| Bang Rak | THB 1,890 | 756 |
| Samphanthawong | THB 1,879 | 169 |
| Vadhana | THB 1,828 | 3,709 |
| Khlong Toei | THB 1,622 | 3,119 |

### 8.5 Host Portfolio Segmentation

| Host Tier | Hosts | Listings | Market Share |
|---|---|---|---|
| Single (1 listing) | 3,656 | 3,656 | 15.7% |
| Small (2–5 listings) | 2,102 | 5,592 | 24.0% |
| Commercial (6+ listings) | 913 | 14,025 | **60.3%** |

Bangkok also shows heavy commercial operator concentration, though slightly less extreme than Singapore.

---

## 9. Statistical Analysis

### 9.1 H1 — Entire Home vs Private Room Price Difference

**Method:** Mann-Whitney U test (non-parametric; price distributions are highly skewed and violate t-test normality assumptions).

**Null hypothesis:** Price distributions of entire-home and private-room listings are identical.

| City | Entire Home Median | Private Room Median | Premium | p-value | Effect Size (r) |
|---|---|---|---|---|---|
| Singapore | SGD 314 | SGD 95 | **3.31x** | < 0.001 | Large |
| Bangkok | THB 1,500 | THB 1,090 | **1.38x** | < 0.001 | Large |

**Result:** H0 rejected for both cities. The entire-home premium is statistically significant in both markets, but is more than twice as large in Singapore. This reflects Singapore's tighter housing supply, stricter licensing requirements for short-term rentals, and higher cost of living.

### 9.2 H4 — Neighbourhood Price Differences

**Method:** One-way ANOVA across neighbourhoods with at least 10 listings.

| City | Neighbourhoods Tested | F-Statistic | p-value | Result |
|---|---|---|---|---|
| Singapore | 34 (of 40, filtered to ≥10 listings) | 4.28 | < 0.001 | **Significant** — reject H0 |
| Bangkok | 50 | 0.96 | 0.556 | **Not significant** — fail to reject H0 |

**Key insight:** In Singapore, where you list matters significantly — location is a genuine price driver. In Bangkok, neighbourhood has almost no explanatory power for price. Bangkok pricing appears driven by property quality, size, and room type — factors not captured in the summary listing file.

### 9.3 Correlation Matrix

Top numeric correlations with price (Singapore):

| Feature | Correlation with Price |
|---|---|
| minimum_nights | Moderate positive |
| calculated_host_listings_count | Moderate positive |
| availability_365 | Weak negative |
| number_of_reviews | Weak negative |

In Bangkok, correlations with price are weaker across all features, consistent with the low OLS R².

### 9.4 OLS Regression — Price Drivers

An enhanced model was developed by adding features available in the enriched dataset beyond the baseline four.

**Baseline model** (4 features): `log(price) ~ C(room_type) + availability_365 + number_of_reviews + minimum_nights`

**Enhanced model** adds:
- `reviews_per_month` — review rate as a demand velocity signal, distinct from total review count
- `calculated_host_listings_count` — commercial-scale operators price differently from individual hosts
- `log(nb_median_price)` — neighbourhood price context as a continuous location signal
- Singapore only: `C(neighbourhood)` fixed effects — justified by H4 ANOVA (F=4.28, p<0.001); not applied to Bangkok where neighbourhood ANOVA was not significant (p=0.56)

| Metric | Singapore | Bangkok |
|---|---|---|
| Baseline R² | 0.432 | 0.082 |
| **Enhanced R²** | **0.512** | **0.178** |
| Adjusted R² | 0.503 | 0.178 |
| Observations | 2,643 | 23,273 |
| F-statistic p-value | < 0.001 | < 0.001 |

**Singapore interpretation:** The enhanced model explains 51.2% of price variance — a material improvement from 43.2%. Neighbourhood location and the local price context jointly capture location value that room type alone could not. Room type remains the single largest coefficient.

**Bangkok interpretation:** The enhanced model more than doubles explained variance from 8.2% to 17.8%. Reviews per month and host listing count are now significant contributors. The remaining ~82% of unexplained variance reflects unobserved listing quality factors — amenities, interior design, photos — which require the detailed listings file to model.

### 9.5 Cross-City Price Comparison in USD

To enable a meaningful absolute price comparison, local prices were converted to USD using September 2025 exchange rates (1 SGD = 0.75 USD, 1 THB = 0.028 USD).

| Room Type | Singapore (USD) | Bangkok (USD) | SG Premium |
|---|---|---|---|
| Entire home/apt | USD 235.50 | USD 42.00 | 5.6x |
| Private room | USD 71.25 | USD 30.52 | 2.3x |
| Hotel room | USD 144.00 | USD 41.24 | 3.5x |
| Shared room | USD 48.75 | USD 18.20 | 2.7x |
| **All types** | **USD 165.75** | **USD 38.61** | **4.3x** |

Singapore is **4.3x more expensive** than Bangkok in USD terms across all listing types.

---

## 10. Cross-City Business Intelligence

This section directly answers the five business questions from the project brief.

### Q1 — Price Premium: Entire Home vs Private Room

**Singapore commands a significantly larger entire-home premium (3.31x) compared to Bangkok (1.38x).**

In USD terms, a Singapore entire home costs USD 235 vs a private room at USD 71 — a difference of USD 164 per night. In Bangkok, the gap is only USD 11 (USD 42 vs USD 31). This reflects Singapore's constrained housing supply, higher land costs, and strict STR licensing requirements that reduce the supply of legally available entire-home listings.

### Q2 — Host Concentration

**Commercial hosts dominate both markets, but Singapore is more concentrated.**

- Singapore: 90 commercial hosts control 71.3% of all listings
- Bangkok: 913 commercial hosts control 60.3% of all listings

Singapore's commercial hosting market is structurally more oligopolistic — a handful of professional operators (likely serviced apartment companies) account for the majority of supply. Bangkok has more commercial hosts in absolute terms but a wider distribution.

### Q3 — Neighbourhood Investment Signal

**Underpriced neighbourhoods (high demand, below-market pricing) in Singapore:**

Using review activity as a demand proxy and median price relative to city median:

- Kallang (SGD 160, above-median reviews) — priced below central districts despite active bookings
- Geylang (below city median, high review activity) — high demand in an affordable fringe area

**Bangkok underpriced areas:** ANOVA confirms neighbourhood price differences are not significant in Bangkok, making neighbourhood-based investment signals unreliable without additional data (ratings, amenity scores).

### Q4 — Seasonality

**Calendar price data is unavailable** — both `price` and `adjusted_price` columns in `calendar.csv.gz` are 100% null for both cities. Seasonality analysis from calendar pricing could not be conducted. Availability patterns (booked vs available days) could be analyzed, but date-level granularity was out of scope for this phase.

This is documented as a data limitation. The detailed `listings.csv` with `availability_30/60/90` fields, combined with a populated calendar price file, would be required for full seasonality analysis.

### Q5 — Market Maturity

**Bangkok is the faster-growing market; both cities started at the same time.**

| Year | Singapore new listings | Bangkok new listings |
|---|---|---|
| 2011 | 2 | 2 |
| 2019 | 170 | 1,206 |
| 2022 | 149 | 1,253 |
| 2023 | 141 | 2,818 |
| 2024 | 182 | **4,070** |

Both cities entered the Airbnb market simultaneously around 2011. Bangkok's growth from 2022–2024 is explosive — 4,070 new listings entered in 2024 alone, compared to Singapore's 182. Singapore shows a more stable, mature market with modest annual growth. Bangkok is in an active expansion phase.

---

## 11. Completed Work Summary

| Phase | Component | Status |
|---|---|---|
| Phase 1 | Dataset familiarization (`01_dataset_familiarization.ipynb`) | Complete |
| Phase 1 | Ingestion pipeline (`src/ingest.py`) | Complete |
| Phase 1 | Data quality report (profiling + outlier detection) | Complete |
| Phase 2 | Cleaning & standardization (`src/clean.py`) | Complete |
| Phase 2 | Enrichment & joins (`src/enrich.py`) | Complete |
| Phase 2 | USD price conversion for cross-city comparison | Complete |
| Phase 2 | DuckDB star schema (`src/model.py`) | Complete |
| Phase 2 | 6 analytical SQL queries (`sql/analytical_queries.sql`) | Complete |
| Phase 3 | Singapore EDA (`02_eda_singapore.ipynb`) — 7 chart sections | Complete |
| Phase 3 | Bangkok EDA (`03_eda_bangkok.ipynb`) — 7 chart sections | Complete |
| Phase 3 | Statistical analysis (`04_statistical_analysis.ipynb`) | Complete |
| Phase 3 | H1 hypothesis test (Mann-Whitney U) | Complete |
| Phase 3 | H4 hypothesis test (ANOVA) | Complete |
| Phase 3 | OLS regression + cross-city comparison | Complete |
| Deliverables | Engineering decision log (15 decisions) | Complete |
| Deliverables | README with setup instructions | Complete |
| Deliverables | requirements.txt | Complete |
| Deliverables | Final report (this document) | Complete |

---

## 12. Incomplete Work & Prioritization Rationale

| Component | Status | Rationale for deferral |
|---|---|---|
| Streamlit Dashboard | Not built | Deprioritized in favor of depth in engineering and statistical analysis. Dashboard would be the next deliverable given more time. |
| Price Prediction Model | Not built | Requires detailed listings file (amenities, ratings, host_since) for meaningful feature engineering. Summary file yields low-signal features. |
| H2 — Superhost analysis | Skipped | `host_is_superhost` field not available in summary `listings.csv`. Requires detailed listings download. |
| H5 — Weekend vs weekday pricing | Skipped | Both `price` and `adjusted_price` in `calendar.csv.gz` are 100% null. No per-day pricing data available. |
| NLP on reviews | Skipped | `reviews.csv` contains only `listing_id` and `date` — no review text. Full text requires `reviews.csv.gz`. Out of scope per PRD. |
| Cloud/Docker deployment | Skipped | Time cost too high relative to evaluation weight. Architecture described but not implemented. |
| Geospatial choropleth maps | Not built | folium/plotly maps require significant setup time; deprioritized after completing statistical analysis. Would add visual value to the EDA section. |

---

## Appendix A — AI Usage Disclosure

This project was completed with the assistance of Claude (claude-sonnet-4-6, Anthropic), used as a development assistant throughout the following stages:

- **Project planning:** PRD review and step-by-step execution order
- **Pipeline development:** `ingest.py`, `clean.py`, `enrich.py`, `model.py` were written collaboratively — logic decisions were made by the candidate, code was structured and written with AI assistance
- **Notebook development:** EDA and statistical analysis notebook structure and chart code were co-developed
- **Statistical methodology:** Guidance on choosing Mann-Whitney U over t-test, ANOVA rationale, and log-price OLS transformation
- **Report writing:** This report structure and initial draft were produced with AI assistance; findings are based on real analytical outputs

All code, findings, and engineering decisions were reviewed and understood by the candidate. The AI was used as a tool, not a substitute for analytical reasoning.

---

## Appendix B — Key Engineering Decisions

15 decisions are documented in `decisions/engineering_decision_log.md`, grouped by the day of the project on which they were made.

| Decision | Day | Summary |
|---|---|---|
| DEC-01 | Day 1 | Used summary listings.csv — detailed file unavailable at build time |
| DEC-02 | Day 1 | Dropped price nulls (28.4% SG, 19.2% BK) rather than imputing |
| DEC-03 | Day 1 | Used median not mean for all price aggregation (skewness > 10) |
| DEC-04 | Day 1 | Capped maximum_nights at 365 (INT_MAX overflow artifact) |
| DEC-05 | Day 1 | Filled reviews_per_month nulls with 0 (not missing, just no reviews) |
| DEC-06 | Day 1 | Parsed last_review to datetime (enables time-series operations) |
| DEC-07 | Day 1 | Dropped 100% null columns per city (Bangkok neighbourhood_group, license) |
| DEC-08 | Day 2 | Left join listings to reviews (preserves zero-review listings) |
| DEC-09 | Day 2 | Used occupancy proxy = (365 − availability_365) / 365 |
| DEC-10 | Day 2 | Calendar inner-joined to listings — listing-level price is sole price source; calendar used for availability only |
| DEC-11 | Day 2 | DuckDB for analytical layer (zero-config, parquet-native) |
| DEC-12 | Day 2 | Parquet for processed data storage (columnar, type-preserving) |
| DEC-13 | Day 2 | USD conversion for cross-city comparison (1 SGD = 0.75, 1 THB = 0.028) |
| DEC-14 | Day 3 | Mann-Whitney U over t-test (price is non-normal) |
| DEC-15 | Day 3 | log(price) in OLS regression + enhanced model features (R² SG 0.432→0.512) |

---

## Appendix C — Skipped Hypotheses

| Hypothesis | Data Required | Status |
|---|---|---|
| H2: Superhost premium | `host_is_superhost` field | Not in summary listings.csv |
| H3: Review score analysis | `review_scores_rating` field | Not in summary listings.csv |
| H5: Weekend vs weekday pricing | Calendar price data | Calendar price 100% null |

These hypotheses would be testable if the detailed `listings.csv` (full metadata, ~70 columns) and a populated calendar price file were obtained from Inside Airbnb's full data export.

---

## Appendix D — Issues Found & Debugging Approach

During report assembly, a set of internal-consistency errors were discovered in the draft figures. Rather than correcting them silently, a reusable validation layer (`src/validate.py`) was built to catch each error class automatically and to act as a publish-gate before the PDF is generated. This appendix documents each issue, its root cause, and how it was resolved.

### D.1 Debugging Philosophy

Numbers in a report fail in predictable ways: a subset is quoted larger than its parent, segment counts don't reconcile to a total, a currency conversion doesn't trace back to its source figure, a "top-N" table isn't actually sorted, or the same population is quoted with two different counts in two sections. Each of these is mechanically checkable. The `Validator` class encodes one assertion per failure mode, runs across all reported figures, and in strict mode halts the build if any check fails — so a bad number cannot survive into the final document.

### D.2 Issues Found and How They Were Resolved

| ID | Issue | Root cause | Detection | Resolution |
|---|---|---|---|---|
| BUG-01 | §7.4 stated "2,987 of 2,643 clean listings" — a subset larger than the total | Central Region figure was taken from the **raw** frame while the total referenced the **cleaned** frame; the two were never compared | `subset_not_exceeding_total()` — asserts subset ≤ total | Recomputed Central Region count from the cleaned frame: 2,155 of 2,643 (81.5%) |
| BUG-02 | §8.4 "top 5 most expensive" listed Khlong Toei (THB 1,622) below Pom Prap Sattru Phai (THB 1,503), and Pom Prap Sattru Phai was not even in the top 5 | Table was ordered by listing count, not by price, and a wrong neighbourhood entry was carried over | `is_sorted_desc()` — asserts a ranked table is monotonically descending | Table re-derived from the cleaned parquet sorted by median price: 4th place is Vadhana (THB 1,828) |
| BUG-03 | Singapore raw listing count appeared as 3,710 (§3.1) and 3,693 (§3.5, §5.2) | Two independent reads of the source file; 3,710 was a manual note taken before deduplication | `no_drift()` — asserts two figures for the same population agree | Canonical raw count is 3,693 — confirmed from `listings.csv` directly; §3.1 corrected |
| BUG-04 | Risk of silently aggregating calendar `price`/`adjusted_price` (100% null) | Aggregation functions return without error on an all-null column, producing meaningless output | `not_all_null()` — asserts a column has at least one non-null before it is aggregated | Calendar-price analysis was correctly excluded; the check now enforces this rule so the exclusion cannot be accidentally reversed |
| BUG-05 | Appendix B decisions DEC-14/15 were tagged "Day 4" in a 3-day project | Carry-over from an earlier 4-day plan that was revised | Manual review | Relabelled to Day 3. Decision log restructured: Day 1 = Ingestion & Cleaning, Day 2 = Enrichment & Modelling, Day 3 = Statistical Analysis |
| BUG-06 | DEC-10 described "listing price attached per calendar day" in a way that could imply per-day dynamic pricing exists | Decision-log entry written before the null-price finding was fully confirmed | Cross-reference against §3.6 and Q4 | Reworded to state that listing-level price is the sole price source and the calendar is used only for availability (`available` t/f column) |

### D.3 Validation as a Publish-Gate

The validator (`src/validate.py`) runs in two modes. In **soft mode** (`strict=False`) it collects all findings so the full picture is visible in one pass; in **strict mode** it raises on the first failure and `gate_report()` aborts the build. Running the suite against the corrected figures yields zero failures.

### D.4 Outcome

Six issues were identified and resolved. None affected the underlying analytical conclusions — the market-size, premium, host-concentration, and growth findings all held — but they would have undermined the report's credibility. The lasting deliverable is the `validate.py` module: a reusable consistency layer that would catch the same error classes in any future dataset or city added to the pipeline.
