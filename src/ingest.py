"""
ingest.py — Entry point for the Airbnb pipeline.

Responsibilities:
  1. load_city       : reads all raw files for a given city into DataFrames
  2. profile_df      : computes quality stats for one DataFrame
  3. run_ingestion   : orchestrates load + profile, prints report, returns data
"""

import pandas as pd
import numpy as np
from pathlib import Path


# ── Section 1: Load ──────────────────────────────────────────────────────────
# Returns a dict so downstream functions can loop over files without hardcoding
# names. Plain .csv preferred over .csv.gz where both exist (faster to read).

def load_city(city: str, data_dir: str) -> dict[str, pd.DataFrame]:
    """
    Load all raw files for a city.

    Parameters
    ----------
    city     : 'singapore' or 'bangkok'
    data_dir : path to the data/raw/ root folder

    Returns
    -------
    dict with keys: 'listings', 'reviews', 'neighbourhoods', 'calendar'
    """
    root = Path(data_dir) / city

    files = {
        "listings":       root / "listings.csv",
        "reviews":        root / "reviews.csv",
        "neighbourhoods": root / "neighbourhoods.csv",
        "calendar":       root / "calendar.csv.gz",   # only available compressed
    }

    # Validate all expected files exist before loading anything
    missing = [name for name, path in files.items() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"[{city}] Missing files: {missing}")

    print(f"\nLoading {city} data...")
    data = {}
    for name, path in files.items():
        compression = "gzip" if path.suffix == ".gz" else None
        data[name] = pd.read_csv(path, compression=compression, low_memory=False)
        print(f"  {name:20s} {data[name].shape[0]:>10,} rows  x  {data[name].shape[1]} cols")

    return data


# ── Section 2: Profile ────────────────────────────────────────────────────────
# Per-column stats. Skewness flags whether mean or median should be trusted.
# High skew (>1) means the mean is being pulled by outliers — use median instead.

def profile_df(df: pd.DataFrame, name: str) -> pd.DataFrame:
    """
    Compute per-column quality stats for one DataFrame.

    Returns a DataFrame with one row per column containing:
    dtype, null_count, null_pct, cardinality,
    and for numeric columns: min, max, mean, median, skewness.
    """
    rows = []

    for col in df.columns:
        series = df[col]
        null_count = series.isnull().sum()
        null_pct   = round(null_count / len(df) * 100, 2)
        cardinality = series.nunique(dropna=True)

        row = {
            "dataframe":   name,
            "column":      col,
            "dtype":       str(series.dtype),
            "null_count":  null_count,
            "null_pct":    null_pct,
            "cardinality": cardinality,
            "min":         None,
            "max":         None,
            "mean":        None,
            "median":      None,
            "skewness":    None,
        }

        # Numeric columns get distribution stats
        if pd.api.types.is_numeric_dtype(series):
            clean = series.dropna()
            if len(clean) > 0:
                row["min"]      = round(clean.min(), 2)
                row["max"]      = round(clean.max(), 2)
                row["mean"]     = round(clean.mean(), 2)
                row["median"]   = round(clean.median(), 2)
                row["skewness"] = round(clean.skew(), 2)

        rows.append(row)

    return pd.DataFrame(rows)


# ── Section 3: Outlier Detection ─────────────────────────────────────────────
# Flags rows where numeric values are extreme (beyond 3 standard deviations).
# This surfaces bad data (e.g. ฿1,000,000 listing) before cleaning.

def detect_outliers(df: pd.DataFrame, columns: list[str], city: str) -> pd.DataFrame:
    """
    Flag rows where a column value is beyond 3 std deviations from the mean.
    Returns a summary DataFrame of outlier counts per column.
    """
    results = []
    for col in columns:
        if col not in df.columns:
            continue
        series = df[col].dropna()
        if not pd.api.types.is_numeric_dtype(series):
            continue
        mean  = series.mean()
        std   = series.std()
        upper = mean + 3 * std
        lower = mean - 3 * std
        outliers = df[(df[col] < lower) | (df[col] > upper)]
        results.append({
            "city":           city,
            "column":         col,
            "outlier_count":  len(outliers),
            "outlier_pct":    round(len(outliers) / len(df) * 100, 2),
            "lower_bound":    round(lower, 2),
            "upper_bound":    round(upper, 2),
            "actual_max":     round(df[col].max(), 2),
        })
    return pd.DataFrame(results)


# ── Section 4: Data Quality Report ───────────────────────────────────────────
# Prints a readable summary. In a real pipeline this would write an HTML file.
# Here we print tables so the report is visible directly in the terminal.

def print_quality_report(profiles: dict[str, pd.DataFrame], outlier_summary: pd.DataFrame, city: str):
    """Print a formatted data quality report for a city."""
    print(f"\n{'='*60}")
    print(f"  DATA QUALITY REPORT — {city.upper()}")
    print(f"{'='*60}")

    for name, profile in profiles.items():
        print(f"\n--- {name} ---")
        # Only show columns that have issues (nulls or extreme skew)
        skew_flag = profile["skewness"].astype(float).abs() > 1
        flagged = profile[
            (profile["null_pct"] > 0) | skew_flag.fillna(False)
        ].copy()

        if flagged.empty:
            print("  No quality issues detected.")
        else:
            print(flagged[["column", "dtype", "null_pct", "skewness", "min", "max", "median"]].to_string(index=False))

    print(f"\n--- Outlier Summary ---")
    if outlier_summary.empty:
        print("  No outliers detected.")
    else:
        print(outlier_summary.to_string(index=False))


# ── Section 5: Orchestrator ───────────────────────────────────────────────────
# This is the single function you call from a notebook or CLI.
# It wires load → profile → outlier detection → report together.

def run_ingestion(city: str, data_dir: str) -> dict[str, pd.DataFrame]:
    """
    Full ingestion pipeline for one city.

    Parameters
    ----------
    city     : 'singapore' or 'bangkok'
    data_dir : path to the data/raw/ root folder

    Returns
    -------
    dict of raw DataFrames (same as load_city)
    """
    # Step 1 — Load
    data = load_city(city, data_dir)

    # Step 2 — Profile each file
    profiles = {name: profile_df(df, name) for name, df in data.items()}

    # Step 3 — Detect outliers in key numeric columns
    outlier_cols = ["price", "availability_365", "minimum_nights", "number_of_reviews"]
    outliers = detect_outliers(data["listings"], outlier_cols, city)

    # Step 4 — Print report
    print_quality_report(profiles, outliers, city)

    return data


# ── CLI entry point ───────────────────────────────────────────────────────────
# Lets you run this directly: python src/ingest.py singapore
# Without this block, the functions only run when imported.

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python ingest.py <city>")
        print("       city = 'singapore' or 'bangkok'")
        sys.exit(1)

    city_arg    = sys.argv[1].lower()
    data_dir    = Path(__file__).parent.parent / "data" / "raw"
    run_ingestion(city_arg, str(data_dir))
