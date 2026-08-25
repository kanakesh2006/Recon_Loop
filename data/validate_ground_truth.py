"""Ground-truth validation for ReconLoop synthetic data.

Reads ground_truth.csv plus the three source CSVs and asserts the batch is
internally consistent and complete. Exits 0 on valid data, 1 with clear
error messages on invalid data.

Usage:
    python data/validate_ground_truth.py [--data-dir data/samples]
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from generate_synthetic import (  # noqa: E402
    BUNDLE_SIZE,
    EDGE_CASE_COUNTS,
)

MIN_TOTAL_EVENTS = 50


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def validate(data_dir: Path) -> list[str]:
    errors: list[str] = []

    ledger = read_csv(data_dir / "internal_ledger.csv")
    settlements = read_csv(data_dir / "gateway_settlement.csv")
    bank = read_csv(data_dir / "bank_statement.csv")
    ground_truth = read_csv(data_dir / "ground_truth.csv")

    # (a) total record count >= 50
    if len(ground_truth) < MIN_TOTAL_EVENTS:
        errors.append(
            f"ground_truth.csv has {len(ground_truth)} events; minimum is {MIN_TOTAL_EVENTS}"
        )

    ledger_order_ids = {row["order_id"] for row in ledger}
    settlement_ids = {row["settlement_id"] for row in settlements}
    bank_references = {row["reference_no"] for row in bank}
    settlement_txn_refs = {row["txn_ref"] for row in settlements}

    # (b) every ground-truth order_id exists in the ledger
    gt_order_ids = {row["order_id"] for row in ground_truth}
    missing = gt_order_ids - ledger_order_ids
    if missing:
        errors.append(f"ground-truth order_ids missing from ledger: {sorted(missing)}")
    extra = ledger_order_ids - gt_order_ids
    if extra:
        errors.append(f"ledger order_ids missing from ground truth: {sorted(extra)}")

    # (c) edge-case counts match the spec (bundled events count per order)
    label_counts: dict[str, int] = {}
    for row in ground_truth:
        label_counts[row["edge_case_label"]] = (
            label_counts.get(row["edge_case_label"], 0) + 1
        )
    for label, expected in EDGE_CASE_COUNTS.items():
        actual = label_counts.get(label, 0)
        wanted = expected * BUNDLE_SIZE if label == "bundled_match" else expected
        if actual != wanted:
            errors.append(
                f"edge case '{label}': expected {wanted} events, found {actual}"
            )
    if "clean_match" not in label_counts:
        errors.append("no clean_match events found")

    # (d) pending records have no settlement/bank rows
    for row in ground_truth:
        if row["edge_case_label"] != "pending":
            continue
        if row["settlement_id"] or row["bank_reference"]:
            errors.append(
                f"pending event {row['order_id']} has settlement_id/bank_reference set"
            )
        if row["order_id"] in settlement_txn_refs:
            errors.append(
                f"pending event {row['order_id']} has a settlement row in gateway_settlement.csv"
            )

    # Referential integrity for every non-pending event
    for row in ground_truth:
        if row["edge_case_label"] == "pending":
            continue
        if row["settlement_id"] not in settlement_ids:
            errors.append(
                f"event {row['order_id']} references missing settlement {row['settlement_id']}"
            )
        if row["bank_reference"] not in bank_references:
            errors.append(
                f"event {row['order_id']} references missing bank row {row['bank_reference']}"
            )

    # Settlement rows must link to a ledger order
    for row in settlements:
        if row["txn_ref"] not in ledger_order_ids:
            errors.append(
                f"settlement {row['settlement_id']} has unknown txn_ref {row['txn_ref']}"
            )

    # Bundled payouts: exactly one bank row per shared payout UTR
    utr_counts: dict[str, int] = {}
    for row in bank:
        utr = (
            row["reference_no"].split("/")[1]
            if "/" in row["reference_no"]
            else row["reference_no"]
        )
        utr_counts[utr] = utr_counts.get(utr, 0) + 1
    bundled_utrs = {
        row["bank_reference"].split("/")[1]
        for row in ground_truth
        if row["edge_case_label"] == "bundled_match"
    }
    for utr in bundled_utrs:
        if utr_counts.get(utr, 0) != 1:
            errors.append(
                f"bundled payout UTR {utr} should appear on exactly 1 bank row"
            )

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate ReconLoop ground-truth batch."
    )
    parser.add_argument(
        "--data-dir", default="data/samples", help="directory with the 4 CSVs"
    )
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir)
    required = [
        "internal_ledger.csv",
        "gateway_settlement.csv",
        "bank_statement.csv",
        "ground_truth.csv",
    ]
    missing_files = [name for name in required if not (data_dir / name).exists()]
    if missing_files:
        print(f"ERROR: missing files in {data_dir}: {missing_files}")
        print("Run: python data/generate_synthetic.py --count 60 --output data/samples")
        return 1

    errors = validate(data_dir)

    ground_truth = read_csv(data_dir / "ground_truth.csv")
    label_counts: dict[str, int] = {}
    for row in ground_truth:
        label_counts[row["edge_case_label"]] = (
            label_counts.get(row["edge_case_label"], 0) + 1
        )

    print(f"Validating batch in {data_dir}")
    print(f"  ground-truth events: {len(ground_truth)}")
    print("  edge-case distribution:")
    for label in sorted(label_counts):
        print(f"    {label:<16} {label_counts[label]}")

    if errors:
        print(f"\nFAILED - {len(errors)} error(s):")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("\nOK - ground truth is internally consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
