"""
enrich.py — Joins, derived fields, and cross-city master table.

Steps:
  1. Summarise reviews → one row per listing (count, first date, last date)
  2. Left join listings + review summary (keep listings with zero reviews)
  3. Derive new columns: days_since_last_review, occupancy_proxy,
                         price_per_review, price_usd (cross-city comparison)
  4. Compute neighbourhood-level aggregates and join back
  5. Stack both cities into a single master_listings table
  6. Enrich calendar — inner join calendar + listings to recover price per day,
     tag weekend/weekday, extract date parts for H5 and seasonality analysis
  7. Save all outputs to data/processed/
"""

import pandas as pd
import numpy as np
from pathlib import Path

SNAPSHOT_DATE = pd.Timestamp("2025-09-28")   # approximate Inside Airbnb scrape date

# Exchange rates as of scrape date (Sep 2025, sourced from xe.com historical rates).
# Used to convert local prices to USD for cross-city comparison only.
# Local currency columns (price) are preserved alongside price_usd.
FX_TO_USD = {
    "singapore": 0.75,   # 1 SGD = 0.75 USD
    "bangkok":   0.028,  # 1 THB = 0.028 USD
}


# ── Step 1: Summarise reviews ─────────────────────────────────────────────────
# reviews.csv has one row per review. We need one row per listing before
# joining. groupby + agg collapses many rows → one summary row per listing_id.

def summarise_reviews(reviews: pd.DataFrame) -> pd.DataFrame:
    reviews["date"] = pd.to_datetime(reviews["date"], errors="coerce")
    summary = (
        reviews
        .groupby("listing_id")
        .agg(
            review_count      = ("date", "count"),
            review_first_date = ("date", "min"),
            review_last_date  = ("date", "max"),
        )
        .reset_index()
    )
    return summary


# ── Step 2: Left join listings + reviews ─────────────────────────────────────
# Left join: every listing survives. Listings with zero reviews get NaN in
# review columns — we fill those with 0 / NaT rather than dropping them.

def join_reviews(listings: pd.DataFrame, review_summary: pd.DataFrame) -> pd.DataFrame:
    merged = pd.merge(
        listings,
        review_summary,
        left_on="id",
        right_on="listing_id",
        how="left",
    )
    # Drop the duplicate key column from the right table
    merged = merged.drop(columns=["listing_id"], errors="ignore")

    # Listings with no reviews: fill count with 0, dates stay NaT
    merged["review_count"] = merged["review_count"].fillna(0).astype(int)
    return merged


# ── Step 3: Derived columns ───────────────────────────────────────────────────
# days_since_last_review : activity signal — recent = active listing
# occupancy_proxy        : (365 - availability_365) / 365
#                          Inside Airbnb methodology, not actual bookings
# price_per_review       : price relative to review volume
#                          high price + low reviews = underperforming listing

def add_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    # Days since last review — how recently was this listing active?
    df["days_since_last_review"] = (
        SNAPSHOT_DATE - df["review_last_date"]
    ).dt.days

    # Occupancy proxy — fraction of year that was NOT available
    if "availability_365" in df.columns:
        df["occupancy_proxy"] = ((365 - df["availability_365"]) / 365).round(4)

    # Price per review — only meaningful where review_count > 0
    df["price_per_review"] = np.where(
        df["review_count"] > 0,
        (df["price"] / df["review_count"]).round(2),
        np.nan,
    )

    # Price in USD — enables direct cross-city comparison.
    # Local price columns are kept; price_usd is added alongside them.
    # Exchange rates as of scrape date Sep 2025 (see FX_TO_USD at top of file).
    city = df["city"].iloc[0]
    rate = FX_TO_USD.get(city, 1.0)
    df["price_usd"] = (df["price"] * rate).round(2)

    return df


# ── Step 4: Neighbourhood-level aggregates ────────────────────────────────────
# Computed per city so Singapore and Bangkok neighbourhoods don't mix.
# Joined back as new columns so each listing row carries its neighbourhood
# context — useful for the "underpriced relative to neighbourhood" analysis.

def add_neighbourhood_aggregates(df: pd.DataFrame) -> pd.DataFrame:
    nb_agg = (
        df.groupby(["city", "neighbourhood"])
        .agg(
            nb_listing_count   = ("id",    "count"),
            nb_median_price    = ("price", "median"),
            nb_mean_price      = ("price", "mean"),
        )
        .round(2)
        .reset_index()
    )

    df = pd.merge(df, nb_agg, on=["city", "neighbourhood"], how="left")
    return df


# ── Step 6: Calendar enrichment ──────────────────────────────────────────────
# calendar.csv.gz has price and adjusted_price 100% null.
# Inner join with cleaned listings on listing_id = id to recover:
#   - listing base price (local currency + USD)
#   - room_type and neighbourhood for segmented availability analysis
# Inner join: only keep calendar rows for listings that survived cleaning
# (i.e. had a valid price). This ensures consistency with the rest of the pipeline.
#
# New derived columns:
#   date          → parsed to datetime
#   day_of_week   → 0 = Monday, 6 = Sunday
#   is_weekend    → True for Saturday (5) and Sunday (6)
#   month         → 1–12 for seasonality grouping
#   year          → calendar year
#   available_bool→ True/False from the raw 't'/'f' string

def enrich_calendar(
    calendar: pd.DataFrame,
    listings: pd.DataFrame,
    city: str,
    output_dir: str,
) -> pd.DataFrame:
    """
    Inner join calendar with cleaned listings to attach price and metadata,
    then derive date-based columns for H5 and seasonality analysis.

    Parameters
    ----------
    calendar  : raw calendar DataFrame (from ingest)
    listings  : cleaned listings DataFrame (from clean — already has price_usd)
    city      : 'singapore' or 'bangkok'
    output_dir: path to data/processed/

    Returns
    -------
    Enriched calendar DataFrame saved to calendar_{city}_enriched.parquet
    """
    print(f"\n  Enriching {city} calendar ({len(calendar):,} rows)...")

    # Columns to pull from listings onto each calendar row
    listing_cols = ["id", "price", "price_usd", "room_type", "neighbourhood", "city"]
    listing_lookup = listings[[c for c in listing_cols if c in listings.columns]].drop_duplicates("id")

    # Inner join — only keep calendar rows whose listing_id is in cleaned listings
    # Both tables have a 'price' column: calendar price is 100% null (useless),
    # listing price is what we want. Rename before merging to avoid _x/_y suffixes.
    calendar = calendar.drop(columns=["price", "adjusted_price"], errors="ignore")

    cal = pd.merge(
        calendar,
        listing_lookup,
        left_on="listing_id",
        right_on="id",
        how="inner",
    ).drop(columns=["id"], errors="ignore")

    print(f"    after inner join: {len(cal):,} rows ({len(cal)/len(calendar)*100:.1f}% of raw calendar retained)")

    # Parse date and derive time features
    cal["date"]           = pd.to_datetime(cal["date"], errors="coerce")
    cal["day_of_week"]    = cal["date"].dt.dayofweek          # 0=Mon, 6=Sun
    cal["is_weekend"]     = cal["day_of_week"] >= 5           # Sat=5, Sun=6
    cal["month"]          = cal["date"].dt.month
    cal["year"]           = cal["date"].dt.year

    # Convert available 't'/'f' string → boolean
    cal["available_bool"] = cal["available"].map({"t": True, "f": False})

    # Drop the now-redundant raw available column to avoid confusion
    cal = cal.drop(columns=["available"], errors="ignore")

    out = Path(output_dir)
    save_path = out / f"calendar_{city}_enriched.parquet"
    cal.to_parquet(save_path, index=False)
    print(f"    saved {save_path.name} — {cal.shape[0]:,} rows x {cal.shape[1]} cols")

    return cal


# ── Step 5: Stack into master table ──────────────────────────────────────────
# Concatenate both cities. Columns that exist in one city but not the other
# (e.g. Singapore's licence column) appear as NaN for the other city.

def build_master_table(sg: pd.DataFrame, bk: pd.DataFrame) -> pd.DataFrame:
    master = pd.concat([sg, bk], ignore_index=True)
    return master


# ── Orchestrator ──────────────────────────────────────────────────────────────

def run_enrichment(
    sg_listings:  pd.DataFrame,
    bk_listings:  pd.DataFrame,
    sg_reviews:   pd.DataFrame,
    bk_reviews:   pd.DataFrame,
    output_dir:   str,
    sg_calendar:  pd.DataFrame | None = None,
    bk_calendar:  pd.DataFrame | None = None,
) -> dict:
    """
    Full enrichment pipeline for both cities.

    Parameters
    ----------
    sg_listings / bk_listings : cleaned listings DataFrames (from clean.py)
    sg_reviews  / bk_reviews  : raw reviews DataFrames (from ingest)
    output_dir                : path to data/processed/
    sg_calendar / bk_calendar : raw calendar DataFrames (optional — from ingest)
                                Pass these to enable calendar enrichment and H5.

    Returns
    -------
    dict with keys: 'singapore', 'bangkok', 'master',
                    and optionally 'calendar_singapore', 'calendar_bangkok'
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    results = {}
    for city, listings, reviews in [
        ("singapore", sg_listings, sg_reviews),
        ("bangkok",   bk_listings, bk_reviews),
    ]:
        print(f"\nEnriching {city}...")

        review_summary = summarise_reviews(reviews)
        print(f"  review summary: {len(review_summary):,} listings with reviews")

        df = join_reviews(listings, review_summary)
        print(f"  after join: {len(df):,} rows")

        df = add_derived_columns(df)
        df = add_neighbourhood_aggregates(df)

        df.to_parquet(out / f"{city}_enriched.parquet", index=False)
        print(f"  saved {city}_enriched.parquet — {df.shape[0]:,} rows x {df.shape[1]} cols")
        results[city] = df

    master = build_master_table(results["singapore"], results["bangkok"])
    master.to_parquet(out / "master_listings.parquet", index=False)
    print(f"\nMaster table: {master.shape[0]:,} rows x {master.shape[1]} cols")
    print(f"Saved master_listings.parquet to {out}/")
    results["master"] = master

    # Calendar enrichment — optional, only runs when calendar DataFrames are passed
    for city, calendar, listings in [
        ("singapore", sg_calendar, results["singapore"]),
        ("bangkok",   bk_calendar, results["bangkok"]),
    ]:
        if calendar is not None:
            cal_enriched = enrich_calendar(calendar, listings, city, str(out))
            results[f"calendar_{city}"] = cal_enriched

    return results


# ── CLI entry point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    from pathlib import Path
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from ingest import run_ingestion
    from clean import run_cleaning

    data_raw  = Path(__file__).parent.parent / "data" / "raw"
    data_proc = Path(__file__).parent.parent / "data" / "processed"

    sg_data = run_ingestion("singapore", str(data_raw))
    bk_data = run_ingestion("bangkok",   str(data_raw))

    cleaned = run_cleaning(sg_data["listings"], bk_data["listings"], str(data_proc))

    run_enrichment(
        cleaned["singapore"], cleaned["bangkok"],
        sg_data["reviews"],   bk_data["reviews"],
        str(data_proc),
        sg_calendar=sg_data["calendar"],
        bk_calendar=bk_data["calendar"],
    )
