-- analytical_queries.sql
-- Star schema queries for the Airbnb Market Intelligence DuckDB database.
-- Run after model.py has built the schema.
-- Connect: duckdb data/processed/airbnb.duckdb

-- ── Q1: Price premium — entire home vs private room per city ─────────────────
SELECT
    f.city,
    rt.room_type,
    ROUND(MEDIAN(f.price), 2)   AS median_price,
    COUNT(*)                     AS listing_count
FROM fact_listings f
JOIN dim_room_type rt ON f.room_type_id = rt.room_type_id
WHERE rt.room_type IN ('Entire home/apt', 'Private room')
GROUP BY f.city, rt.room_type
ORDER BY f.city, median_price DESC;

-- ── Q2: Host concentration — what % of the market do commercial hosts control ─
SELECT
    city,
    host_tier,
    COUNT(DISTINCT host_id)                                            AS host_count,
    SUM(host_listing_count)                                            AS total_listings,
    ROUND(SUM(host_listing_count) * 100.0
          / SUM(SUM(host_listing_count)) OVER (PARTITION BY city), 2) AS pct_of_market
FROM (
    SELECT DISTINCT f.city, f.host_id, h.host_listing_count, h.host_tier
    FROM fact_listings f
    JOIN dim_host h ON f.host_id = h.host_id
)
GROUP BY city, host_tier
ORDER BY city, host_tier;

-- ── Q3: Underpriced neighbourhoods — high demand, low price (investment signal)
SELECT
    f.city,
    n.neighbourhood,
    ROUND(MEDIAN(f.price), 2)               AS median_price,
    ROUND(MEDIAN(f.reviews_per_month), 2)   AS median_reviews_pm,
    COUNT(*)                                  AS listing_count
FROM fact_listings f
JOIN dim_neighbourhood n ON f.neighbourhood_id = n.neighbourhood_id
GROUP BY f.city, n.neighbourhood
HAVING COUNT(*) >= 10
ORDER BY f.city, median_reviews_pm DESC, median_price ASC
LIMIT 20;

-- ── Q4: Availability and occupancy by city ───────────────────────────────────
SELECT
    city,
    ROUND(MEDIAN(availability_365), 1)      AS median_available_days,
    ROUND(MEDIAN(occupancy_proxy) * 100, 1) AS median_occupancy_pct,
    ROUND(AVG(availability_365), 1)         AS mean_available_days,
    COUNT(*)                                 AS listing_count
FROM fact_listings
GROUP BY city;

-- ── Q5: Market maturity — new listings entering per year by city ──────────────
SELECT
    city,
    YEAR(review_first_date)                  AS first_review_year,
    COUNT(*)                                  AS listings_entering_market
FROM fact_listings
WHERE review_first_date IS NOT NULL
GROUP BY city, YEAR(review_first_date)
ORDER BY city, first_review_year;

-- ── Q6: Price vs occupancy relationship — bucketed ───────────────────────────
SELECT
    city,
    CASE
        WHEN occupancy_proxy < 0.25 THEN '0-25% occupied'
        WHEN occupancy_proxy < 0.50 THEN '25-50% occupied'
        WHEN occupancy_proxy < 0.75 THEN '50-75% occupied'
        ELSE '75-100% occupied'
    END                              AS occupancy_bucket,
    ROUND(MEDIAN(price), 2)          AS median_price,
    COUNT(*)                         AS listing_count
FROM fact_listings
WHERE occupancy_proxy IS NOT NULL
GROUP BY city, occupancy_bucket
ORDER BY city, occupancy_bucket;
