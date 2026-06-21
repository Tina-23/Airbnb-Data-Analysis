"""
validate.py — Report consistency checks and publish-gate.

Catches the failure modes documented in Appendix D of the final report:
  - Subset larger than total (BUG-01)
  - Top-N table not sorted descending (BUG-02)
  - Same population quoted with two different counts (BUG-03)
  - Aggregating a column that is 100% null (BUG-04)

Usage:
    from src.validate import Validator
    v = Validator(strict=True)      # strict=True raises on first failure
    v.subset_not_exceeding_total("Central Region", 2155, "SG cleaned", 2643)
    v.not_all_null(calendar_df, "price", "calendar price column")
    v.gate_report()                 # prints summary; raises if any failure recorded
"""

import pandas as pd
from typing import Any


class Validator:
    def __init__(self, strict: bool = False):
        self.strict = strict
        self._failures: list[str] = []

    def _fail(self, msg: str) -> None:
        self._failures.append(msg)
        if self.strict:
            raise AssertionError(f"Validation failure: {msg}")
        print(f"  [FAIL] {msg}")

    def _pass(self, msg: str) -> None:
        print(f"  [PASS] {msg}")

    # ── Check 1: subset must not exceed total ────────────────────────────────
    def subset_not_exceeding_total(
        self,
        subset_label: str,
        subset_count: int,
        total_label: str,
        total_count: int,
    ) -> None:
        if subset_count > total_count:
            self._fail(
                f"{subset_label} ({subset_count:,}) exceeds {total_label} ({total_count:,}) "
                f"— subset cannot be larger than its parent population"
            )
        else:
            self._pass(f"{subset_label} ({subset_count:,}) <= {total_label} ({total_count:,})")

    # ── Check 2: top-N table must be sorted descending ───────────────────────
    def is_sorted_desc(self, label: str, values: list[float]) -> None:
        for i in range(len(values) - 1):
            if values[i] < values[i + 1]:
                self._fail(
                    f"{label}: position {i} ({values[i]}) < position {i+1} ({values[i+1]}) "
                    f"— table is not sorted descending"
                )
                return
        self._pass(f"{label}: values are monotonically descending")

    # ── Check 3: no drift — two references to the same population must agree ─
    def no_drift(
        self,
        label: str,
        value_a: Any,
        source_a: str,
        value_b: Any,
        source_b: str,
    ) -> None:
        if value_a != value_b:
            self._fail(
                f"{label}: {source_a} says {value_a} but {source_b} says {value_b} "
                f"— same population quoted with two different figures"
            )
        else:
            self._pass(f"{label}: consistent ({value_a}) across {source_a} and {source_b}")

    # ── Check 4: column must not be 100% null before aggregation ────────────
    def not_all_null(self, df: pd.DataFrame, column: str, label: str) -> None:
        if column not in df.columns:
            self._fail(f"{label}: column '{column}' not found in DataFrame")
            return
        null_pct = df[column].isna().mean() * 100
        if null_pct == 100.0:
            self._fail(
                f"{label}: column '{column}' is 100% null — aggregating it will "
                f"produce meaningless output"
            )
        else:
            self._pass(f"{label}: column '{column}' has {100 - null_pct:.1f}% non-null values")

    # ── Publish-gate ─────────────────────────────────────────────────────────
    def gate_report(self) -> None:
        print(f"\n{'='*55}")
        print(f"VALIDATION GATE — {len(self._failures)} failure(s) / "
              f"{len(self._failures) + self._count_passes()} check(s) run")
        print(f"{'='*55}")
        if self._failures:
            for f in self._failures:
                print(f"  FAIL: {f}")
            raise AssertionError(
                f"Report gate failed with {len(self._failures)} issue(s). "
                f"Fix before generating PDF."
            )
        print("  All checks passed. Safe to generate report.")

    def _count_passes(self) -> int:
        return 0  # tracked via print side-effects; failures are the meaningful count


# ── Standalone validation run ─────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    from pathlib import Path

    DATA = Path("data/processed")
    master = pd.read_parquet(DATA / "master_listings.parquet")
    sg = master[master["city"] == "singapore"]
    bk = master[master["city"] == "bangkok"]

    cal_sg = pd.read_parquet(DATA / "calendar_singapore_enriched.parquet")
    cal_bk = pd.read_parquet(DATA / "calendar_bangkok_enriched.parquet")

    v = Validator(strict=False)

    print("\n--- Checking BUG-01: subset not exceeding total ---")
    central_count = int(sg[sg["neighbourhood_group"] == "Central Region"].shape[0])
    v.subset_not_exceeding_total("Central Region listings", central_count, "SG cleaned total", len(sg))

    print("\n--- Checking BUG-02: Bangkok top-5 table sorted descending ---")
    bk_top5 = (
        bk.groupby("neighbourhood")["price"]
        .median()
        .nlargest(5)
        .reset_index()["price"]
        .tolist()
    )
    v.is_sorted_desc("Bangkok top-5 neighbourhood prices", bk_top5)

    print("\n--- Checking BUG-03: SG raw count consistent ---")
    raw_sg = pd.read_csv("data/raw/singapore/listings.csv")
    v.no_drift(
        "Singapore raw listing count",
        len(raw_sg), "listings.csv direct read",
        3693,        "pipeline canonical figure",
    )

    print("\n--- Checking BUG-04: calendar price is 100% null (guard demonstration) ---")
    # This check demonstrates the guard works: not_all_null() will catch the null
    # column. We run it in soft mode with a fresh validator so it doesn't block the gate —
    # the calendar price exclusion is a known, documented decision (DEC-10).
    raw_cal = pd.read_csv("data/raw/singapore/calendar.csv.gz", nrows=1000)
    guard_v = Validator(strict=False)
    if "price" in raw_cal.columns:
        guard_v.not_all_null(raw_cal, "price", "calendar raw price")
        if guard_v._failures:
            print("  [CONFIRMED] Guard correctly detected 100% null calendar price.")
            print("              Column excluded from analysis per DEC-10 — this is expected.")
    else:
        print("  [INFO] calendar 'price' column not present in this sample")

    v.gate_report()
