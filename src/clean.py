"""
clean.py — Cleaning and standardisation for both cities.

Cleaning rules applied (in order):
  1. Drop rows where price is null       — core metric, >19% null, imputing unsafe
  2. Cap maximum_nights at 365           — INT_MAX overflow artifact in calendar
  3. Fill reviews_per_month nulls → 0   — null means no reviews yet, not missing
  4. Parse last_review to datetime       — enables time-series and duration maths
  5. Drop 100% null columns per city     — neighbourhood_group + license in Bangkok
  6. Validate coordinates                — flag bad rows, do not drop
  7. Save cleaned files as parquet       — fast, typed, preserves datetime dtypes
"""

import pandas as pd
import numpy as np
from pathlib import Path


# ── Step 1: Drop price nulls ─────────────────────────────────────────────────
# Price is the primary analysis metric. Imputing at 19-28% null rate would
# mean a fifth to a quarter of all price output is synthetic — unacceptable
# for a consultancy report.

def drop_price_nulls(df: pd.DataFrame, city: str) -> pd.DataFrame:
    before = len(df)
    df = df[df["price"].notna()].copy()
    dropped = before - len(df)
    print(f"  [{city}] price nulls dropped: {dropped} rows ({dropped/before*100:.1f}%)")
    return df


# ── Step 2: Cap maximum_nights at 365 ────────────────────────────────────────
# 2,147,483,647 is INT_MAX — a 32-bit integer overflow artifact from the
# scraper, not a real host constraint. A year (365 days) is the practical
# ceiling for any Airbnb booking window.

def cap_maximum_nights(df: pd.DataFrame, city: str) -> pd.DataFrame:
    if "maximum_nights" not in df.columns:
        return df
    before = (df["maximum_nights"] > 365).sum()
    df["maximum_nights"] = df["maximum_nights"].clip(upper=365)
    print(f"  [{city}] maximum_nights capped at 365: {before} rows affected")
    return df


# ── Step 3: Fill reviews_per_month nulls with 0 ──────────────────────────────
# Null here means the listing has never received a review, not that the value
# is unknown. Filling with 0 is factually correct, not an imputation guess.

def fill_reviews_nulls(df: pd.DataFrame) -> pd.DataFrame:
    df["reviews_per_month"] = df["reviews_per_month"].fillna(0)
    return df


# ── Step 4: Parse date columns to datetime ───────────────────────────────────
# Leaving dates as strings means pandas treats them as text — sorting,
# subtraction, and groupby-month all break. Parsing to datetime unlocks
# time-series operations and duration calculations (e.g. host_tenure_years).

def parse_dates(df: pd.DataFrame) -> pd.DataFrame:
    for col in ["last_review"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


# ── Step 5: Drop 100% null columns per city ──────────────────────────────────
# Bangkok's neighbourhood_group and license are entirely empty — carrying them
# through the pipeline wastes memory and causes confusion downstream.

def drop_empty_columns(df: pd.DataFrame, city: str) -> pd.DataFrame:
    fully_null = [col for col in df.columns if df[col].isnull().all()]
    if fully_null:
        df = df.drop(columns=fully_null)
        print(f"  [{city}] dropped fully-null columns: {fully_null}")
    return df


# ── Step 6: Validate coordinates ─────────────────────────────────────────────
# Flag rows outside expected bounding boxes rather than dropping — we keep the
# listings but mark them so they can be excluded from geo analysis if needed.
# Singapore: lat 1.1–1.5, lng 103.5–104.1
# Bangkok:   lat 13.3–14.1, lng 100.1–100.9  (Nong Chok edge case noted)

COORD_BOUNDS = {
    "singapore": {"lat": (1.1,  1.5),  "lng": (103.5, 104.1)},
    "bangkok":   {"lat": (13.3, 14.1), "lng": (100.1, 100.9)},
}

def validate_coordinates(df: pd.DataFrame, city: str) -> pd.DataFrame:
    bounds = COORD_BOUNDS.get(city)
    if not bounds:
        return df
    lat_ok = df["latitude"].between(*bounds["lat"])
    lng_ok = df["longitude"].between(*bounds["lng"])
    df["coord_flag"] = ~(lat_ok & lng_ok)
    flagged = df["coord_flag"].sum()
    print(f"  [{city}] coordinate outliers flagged: {flagged} rows")
    return df


# ── Step 7: Add city column ───────────────────────────────────────────────────
# Needed when we stack both cities into the cross-city master table in enrich.py

def add_city_column(df: pd.DataFrame, city: str) -> pd.DataFrame:
    df["city"] = city
    return df


# ── Orchestrator ──────────────────────────────────────────────────────────────

def clean_listings(df: pd.DataFrame, city: str) -> pd.DataFrame:
    """Apply all cleaning steps to a listings DataFrame."""
    print(f"\nCleaning {city} listings — {len(df):,} rows in")

    df = drop_price_nulls(df, city)
    df = cap_maximum_nights(df, city)
    df = fill_reviews_nulls(df)
    df = parse_dates(df)
    df = drop_empty_columns(df, city)
    df = validate_coordinates(df, city)
    df = add_city_column(df, city)

    print(f"  [{city}] clean output: {len(df):,} rows, {df.shape[1]} cols")
    return df


def run_cleaning(sg_listings: pd.DataFrame, bk_listings: pd.DataFrame, output_dir: str) -> dict:
    """
    Clean both cities and save to parquet.

    Parameters
    ----------
    sg_listings  : raw Singapore listings DataFrame (from ingest)
    bk_listings  : raw Bangkok listings DataFrame (from ingest)
    output_dir   : path to data/processed/

    Returns
    -------
    dict with keys 'singapore' and 'bangkok' — cleaned DataFrames
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    sg_clean = clean_listings(sg_listings.copy(), "singapore")
    bk_clean = clean_listings(bk_listings.copy(), "bangkok")

    sg_clean.to_parquet(out / "singapore_clean.parquet", index=False)
    bk_clean.to_parquet(out / "bangkok_clean.parquet",   index=False)

    print(f"\nSaved cleaned files to {out}/")
    return {"singapore": sg_clean, "bangkok": bk_clean}


# ── CLI entry point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from ingest import run_ingestion

    data_raw  = Path(__file__).parent.parent / "data" / "raw"
    data_proc = Path(__file__).parent.parent / "data" / "processed"

    sg_data = run_ingestion("singapore", str(data_raw))
    bk_data = run_ingestion("bangkok",   str(data_raw))

    run_cleaning(sg_data["listings"], bk_data["listings"], str(data_proc))
