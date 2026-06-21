"""
model.py — DuckDB star schema: fact_listings + dimension tables.

Star schema design:
  fact_listings       — one row per listing, holds all measurable values
  dim_host            — who owns the listing
  dim_neighbourhood   — where the listing is, with neighbourhood aggregates
  dim_room_type       — what type of space it is (used for GROUP BY / WHERE)

Why DuckDB:
  Zero config, runs in-process, reads parquet natively, full SQL support.
  No server to spin up — just import and query.
"""

import duckdb
import pandas as pd
from pathlib import Path

DB_PATH  = Path(__file__).parent.parent / "data" / "processed" / "airbnb.duckdb"
PARQUET  = Path(__file__).parent.parent / "data" / "processed" / "master_listings.parquet"


# ── Build schema ──────────────────────────────────────────────────────────────

def build_star_schema(con: duckdb.DuckDBPyConnection):
    """Create all dimension and fact tables from the master parquet file."""

    # Register the parquet file as a virtual table — DuckDB reads it directly
    con.execute(f"CREATE OR REPLACE VIEW raw AS SELECT * FROM read_parquet('{PARQUET}')")

    # ── dim_room_type ─────────────────────────────────────────────────────────
    # Assign a surrogate integer key to each unique room type.
    # This avoids storing the full string in the fact table millions of times.
    con.execute("""
        CREATE OR REPLACE TABLE dim_room_type AS
        SELECT
            ROW_NUMBER() OVER (ORDER BY room_type) AS room_type_id,
            room_type
        FROM (SELECT DISTINCT room_type FROM raw WHERE room_type IS NOT NULL)
    """)

    # ── dim_host ──────────────────────────────────────────────────────────────
    # One row per host. calculated_host_listings_count tells us whether this
    # host is a single-listing owner or a commercial multi-property operator.
    con.execute("""
        CREATE OR REPLACE TABLE dim_host AS
        SELECT DISTINCT
            host_id,
            host_name,
            calculated_host_listings_count  AS host_listing_count,
            CASE
                WHEN calculated_host_listings_count = 1 THEN 'single'
                WHEN calculated_host_listings_count <= 5 THEN 'small'
                ELSE 'commercial'
            END AS host_tier
        FROM raw
        WHERE host_id IS NOT NULL
    """)

    # ── dim_neighbourhood ─────────────────────────────────────────────────────
    # One row per city + neighbourhood combination.
    # Carries neighbourhood-level aggregates computed in enrich.py.
    con.execute("""
        CREATE OR REPLACE TABLE dim_neighbourhood AS
        SELECT
            ROW_NUMBER() OVER (ORDER BY city, neighbourhood) AS neighbourhood_id,
            city,
            neighbourhood,
            neighbourhood_group,
            ROUND(AVG(nb_median_price), 2)    AS nb_median_price,
            ROUND(AVG(nb_mean_price), 2)      AS nb_mean_price,
            MAX(nb_listing_count)             AS nb_listing_count
        FROM raw
        WHERE neighbourhood IS NOT NULL
        GROUP BY city, neighbourhood, neighbourhood_group
    """)

    # ── fact_listings ─────────────────────────────────────────────────────────
    # Central table — one row per listing, foreign keys to all dimension tables.
    # Holds every measurable value we will aggregate in analysis.
    con.execute("""
        CREATE OR REPLACE TABLE fact_listings AS
        SELECT
            r.id                          AS listing_id,
            r.host_id,
            rt.room_type_id,
            n.neighbourhood_id,
            r.city,
            r.price,
            r.availability_365,
            r.occupancy_proxy,
            r.minimum_nights,
            r.number_of_reviews,
            r.review_count,
            r.reviews_per_month,
            r.days_since_last_review,
            r.price_per_review,
            r.nb_median_price,
            r.latitude,
            r.longitude,
            r.last_review,
            r.review_first_date,
            r.review_last_date
        FROM raw r
        LEFT JOIN dim_room_type   rt ON r.room_type   = rt.room_type
        LEFT JOIN dim_neighbourhood n ON r.neighbourhood = n.neighbourhood
                                     AND r.city          = n.city
    """)

    print("Star schema created:")
    for table in ["dim_room_type", "dim_host", "dim_neighbourhood", "fact_listings"]:
        count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table:25s} {count:>8,} rows")


# ── Analytical SQL queries ────────────────────────────────────────────────────
# These answer the 5 business questions from PRD Section 9.

QUERIES = {
    "Q1_price_premium_by_room_type": """
        -- Q1: Do entire-home listings in Singapore command a larger premium
        --     over private rooms compared to Bangkok?
        SELECT
            f.city,
            rt.room_type,
            ROUND(MEDIAN(f.price), 2)   AS median_price,
            COUNT(*)                     AS listing_count
        FROM fact_listings f
        JOIN dim_room_type rt ON f.room_type_id = rt.room_type_id
        WHERE rt.room_type IN ('Entire home/apt', 'Private room')
        GROUP BY f.city, rt.room_type
        ORDER BY f.city, median_price DESC
    """,

    "Q2_host_concentration": """
        -- Q2: What % of hosts control the majority of listings in each market?
        SELECT
            city,
            host_tier,
            COUNT(DISTINCT host_id)                                AS host_count,
            SUM(host_listing_count)                                AS total_listings,
            ROUND(SUM(host_listing_count) * 100.0
                  / SUM(SUM(host_listing_count)) OVER (PARTITION BY city), 2)
                                                                   AS pct_of_market
        FROM (
            SELECT DISTINCT f.city, f.host_id, h.host_listing_count, h.host_tier
            FROM fact_listings f
            JOIN dim_host h ON f.host_id = h.host_id
        )
        GROUP BY city, host_tier
        ORDER BY city, host_tier
    """,

    "Q3_underpriced_neighbourhoods": """
        -- Q3: Which neighbourhoods are underpriced relative to their review volume?
        --     Signal: median price below city median but high reviews_per_month
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
        LIMIT 20
    """,

    "Q4_availability_by_city": """
        -- Q4: Availability patterns — what fraction of the year is each city available?
        --     Lower availability = higher estimated occupancy.
        SELECT
            city,
            ROUND(MEDIAN(availability_365), 1)          AS median_available_days,
            ROUND(MEDIAN(occupancy_proxy) * 100, 1)     AS median_occupancy_pct,
            ROUND(AVG(availability_365), 1)             AS mean_available_days,
            COUNT(*)                                     AS listing_count
        FROM fact_listings
        GROUP BY city
    """,

    "Q5_market_maturity": """
        -- Q5: Is Bangkok a newer/growing market vs Singapore?
        --     Compare review volume growth by year.
        SELECT
            city,
            YEAR(review_first_date)          AS first_review_year,
            COUNT(*)                          AS listings_first_reviewed_that_year
        FROM fact_listings
        WHERE review_first_date IS NOT NULL
        GROUP BY city, YEAR(review_first_date)
        ORDER BY city, first_review_year
    """,

    "Q6_price_vs_occupancy": """
        -- Q6: Does higher occupancy correlate with higher or lower price?
        --     Bucketed to see the relationship across the distribution.
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
        ORDER BY city, occupancy_bucket
    """,
}


def run_queries(con: duckdb.DuckDBPyConnection):
    """Run all analytical queries and print results."""
    for name, sql in QUERIES.items():
        print(f"\n{'='*60}")
        print(f"  {name}")
        print(f"{'='*60}")
        result = con.execute(sql).df()
        print(result.to_string(index=False))


# ── Orchestrator ──────────────────────────────────────────────────────────────

def run_modeling():
    con = duckdb.connect(str(DB_PATH))
    print(f"Connected to DuckDB at {DB_PATH}")
    build_star_schema(con)
    run_queries(con)
    con.close()
    print(f"\nDatabase saved to {DB_PATH}")


if __name__ == "__main__":
    run_modeling()
