"""ReconLoop synthetic data generator.

Produces a labeled held-out batch across three heterogeneous sources:
  - internal_ledger.csv     (merchant's own records)
  - gateway_settlement.csv  (Razorpay-style gateway settlements)
  - bank_statement.csv      (bank account feed)
plus ground_truth.csv mapping every transaction event to its expected outcome.

Clean records and deliberately-injected edge cases (see docs/raw_schemas.md) are
generated together so ground truth is known before the pipeline ever runs.

Usage:
    python data/generate_synthetic.py --count 60 --output data/samples --seed 42
"""

from __future__ import annotations

import argparse
import csv
import random
import string
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from faker import Faker

PAISE = Decimal("0.01")

LEDGER_COLUMNS = [
    "order_id",
    "customer_name",
    "amount",
    "currency",
    "order_date",
    "payment_method",
    "status",
    "notes",
]
SETTLEMENT_COLUMNS = [
    "settlement_id",
    "txn_ref",
    "merchant_id",
    "gross_amount",
    "fee",
    "tax_on_fee",
    "net_amount",
    "settlement_date",
    "utr_number",
    "status",
]
BANK_COLUMNS = ["date", "description", "reference_no", "debit", "credit", "balance"]
GROUND_TRUTH_COLUMNS = [
    "order_id",
    "settlement_id",
    "bank_reference",
    "expected_match_status",
    "edge_case_label",
    "notes",
]

# Edge-case mix from the build doc (Section 6) / implementation plan (P1-04).
# bundled_match: 2 bundles x 3 orders each = 6 events.
EDGE_CASE_COUNTS = {
    "bundled_match": 2,
    "partial_refund": 3,
    "rounding_diff": 4,
    "duplicate_id": 2,
    "date_drift": 3,
    "ref_typo": 3,
    "pending": 3,
    "chargeback": 2,
}
BUNDLE_SIZE = 3

FEE_PCT = Decimal("0.02")
FEE_FLAT = Decimal("3")
TAX_PCT = Decimal("0.18")

BASE_DATE = date(2026, 7, 1)
DATE_SPREAD_DAYS = 30
OPENING_BALANCE = Decimal("500000.00")
PAYMENT_METHODS = ("UPI", "card", "netbanking", "wallet")


def money(value: Decimal) -> str:
    return str(Decimal(value).quantize(PAISE, rounding=ROUND_HALF_UP))


def rand_alnum(n: int) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def gen_order_id() -> str:
    return f"order_{rand_alnum(14)}"


def gen_settlement_id() -> str:
    return f"setl_{rand_alnum(14)}"


def gen_merchant_id() -> str:
    return f"mer_{rand_alnum(14)}"


def gen_utr(on_date: date) -> str:
    # Realistic-looking 22-char Indian UTR: bank code + N + yyyymmdd + 9 digits.
    return f"HDFCN{on_date.strftime('%Y%m%d')}{random.randint(100000000, 999999999)}"


def rand_amount() -> Decimal:
    base = random.choice(
        (
            random.randint(150, 999),
            random.randint(1000, 4999),
            random.randint(5000, 24999),
            random.randint(25000, 99999),
        )
    )
    paise = random.choice((0, 0, 0, 50, 99))
    return Decimal(base) + Decimal(paise) / 100


def calc_fee_tax(gross: Decimal) -> tuple[Decimal, Decimal]:
    fee = (gross * FEE_PCT + FEE_FLAT).quantize(PAISE, rounding=ROUND_HALF_UP)
    tax = (fee * TAX_PCT).quantize(PAISE, rounding=ROUND_HALF_UP)
    return fee, tax


def make_typo(value: str) -> str:
    """Return `value` with one adjacent-char swap or one char dropped."""
    while True:
        chars = list(value)
        i = random.randrange(1, len(chars) - 1)
        if random.random() < 0.5 and i + 1 < len(chars):
            chars[i], chars[i + 1] = chars[i + 1], chars[i]
        else:
            del chars[i]
        mutated = "".join(chars)
        if mutated != value:
            return mutated


class SyntheticGenerator:
    def __init__(self, seed: int):
        random.seed(seed)
        Faker.seed(seed)
        self.fake = Faker()
        self.merchant_id = gen_merchant_id()
        self.ledger_rows: list[dict] = []
        self.settlement_rows: list[dict] = []
        self.bank_rows: list[dict] = []
        self.gt_rows: list[dict] = []

    # ------------------------------------------------------------------ helpers

    def _rand_order_date(self) -> date:
        return BASE_DATE + timedelta(days=random.randint(0, DATE_SPREAD_DAYS - 1))

    def _new_order(self) -> tuple[str, Decimal, date, str, str]:
        return (
            gen_order_id(),
            rand_amount(),
            self._rand_order_date(),
            random.choice(PAYMENT_METHODS),
            self.fake.name(),
        )

    def _add_ledger(
        self,
        order_id: str,
        customer: str,
        amount: Decimal,
        order_date: date,
        method: str,
        status: str,
        notes: str,
    ) -> None:
        self.ledger_rows.append(
            {
                "order_id": order_id,
                "customer_name": customer,
                "amount": money(amount),
                "currency": "INR",
                "order_date": order_date.isoformat(),
                "payment_method": method,
                "status": status,
                "notes": notes,
            }
        )

    def _add_settlement(
        self,
        order_ref: str,
        gross: Decimal,
        fee: Decimal,
        tax: Decimal,
        net: Decimal,
        settle_date: date,
        utr: str,
        status: str,
    ) -> str:
        settlement_id = gen_settlement_id()
        self.settlement_rows.append(
            {
                "settlement_id": settlement_id,
                "txn_ref": order_ref,
                "merchant_id": self.merchant_id,
                "gross_amount": money(gross),
                "fee": money(fee),
                "tax_on_fee": money(tax),
                "net_amount": money(net),
                "settlement_date": settle_date.isoformat(),
                "utr_number": utr,
                "status": status,
            }
        )
        return settlement_id

    def _add_bank(
        self,
        on_date: date,
        description: str,
        reference_no: str,
        credit: Decimal = Decimal("0.00"),
        debit: Decimal = Decimal("0.00"),
    ) -> None:
        self.bank_rows.append(
            {
                "date": on_date.isoformat(),
                "description": description,
                "reference_no": reference_no,
                "debit": money(debit),
                "credit": money(credit),
                "balance": "0.00",  # recomputed chronologically in finalize()
            }
        )

    def _add_gt(
        self,
        order_id: str,
        settlement_id: str,
        bank_reference: str,
        expected: str,
        label: str,
        notes: str,
    ) -> None:
        self.gt_rows.append(
            {
                "order_id": order_id,
                "settlement_id": settlement_id,
                "bank_reference": bank_reference,
                "expected_match_status": expected,
                "edge_case_label": label,
                "notes": notes,
            }
        )

    # ------------------------------------------------------------------ events

    def _matched_event(
        self,
        *,
        label: str,
        notes: str,
        lag_range: tuple[int, int] = (1, 2),
        net_delta: Decimal = Decimal("0.00"),
        ledger_status: str = "completed",
        typo_bank_ref_of: str | None = None,
    ) -> None:
        """One order flowing through ledger -> settlement -> bank, with knobs
        for the amount-tolerance and date-drift edge cases."""
        order_id, amount, order_date, method, customer = self._new_order()
        settle_date = order_date + timedelta(days=random.randint(*lag_range))
        fee, tax = calc_fee_tax(amount)
        net = amount - fee - tax + net_delta
        utr = gen_utr(settle_date)

        self._add_ledger(
            order_id, customer, amount, order_date, method, ledger_status, notes
        )
        settlement_id = self._add_settlement(
            order_id, amount, fee, tax, net, settle_date, utr, "processed"
        )

        utr_in_ref = typo_bank_ref_of if typo_bank_ref_of else utr
        bank_ref = f"NEFT/{utr_in_ref}/RZPPAYOUT"
        bank_date = settle_date + timedelta(days=random.randint(0, 1))
        self._add_bank(
            bank_date, "RAZORPAY SOFTWARE PVT LTD PAYOUT", bank_ref, credit=net
        )

        self._add_gt(order_id, settlement_id, bank_ref, "matched", label, notes)

    def clean_event(self) -> None:
        self._matched_event(label="clean_match", notes="regular sale")

    def partial_refund_event(self) -> None:
        # net_amount is short by the refund amount; ledger keeps the full order value.
        order_id, amount, order_date, method, customer = self._new_order()
        settle_date = order_date + timedelta(days=random.randint(1, 2))
        fee, tax = calc_fee_tax(amount)
        refund = (amount * Decimal(str(random.uniform(0.10, 0.30)))).quantize(
            PAISE, rounding=ROUND_HALF_UP
        )
        net = amount - fee - tax - refund
        utr = gen_utr(settle_date)

        self._add_ledger(
            order_id,
            customer,
            amount,
            order_date,
            method,
            "completed",
            f"partial refund of Rs {money(refund)} issued",
        )
        settlement_id = self._add_settlement(
            order_id, amount, fee, tax, net, settle_date, utr, "refund"
        )

        bank_ref = f"NEFT/{utr}/RZPPAYOUT"
        bank_date = settle_date + timedelta(days=random.randint(0, 1))
        self._add_bank(
            bank_date, "RAZORPAY SOFTWARE PVT LTD PAYOUT", bank_ref, credit=net
        )

        self._add_gt(
            order_id,
            settlement_id,
            bank_ref,
            "matched",
            "partial_refund",
            f"net short by refund Rs {money(refund)}",
        )

    def rounding_diff_event(self) -> None:
        # Fee/tax rounding leaves net_amount off by Rs 0.01 - Rs 2.00.
        delta = Decimal(random.randint(1, 200)) / 100 * random.choice((1, -1))
        self._matched_event(
            label="rounding_diff",
            notes=f"fee/tax rounding difference of Rs {money(delta)}",
            net_delta=delta,
        )

    def date_drift_event(self) -> None:
        self._matched_event(
            label="date_drift",
            notes="delayed settlement: 3-5 day lag",
            lag_range=(3, 5),
        )

    def duplicate_id_event(self) -> None:
        # Same order_id entered twice in the ledger; settlement/bank exist once.
        order_id, amount, order_date, method, customer = self._new_order()
        settle_date = order_date + timedelta(days=random.randint(1, 2))
        fee, tax = calc_fee_tax(amount)
        net = amount - fee - tax
        utr = gen_utr(settle_date)

        self._add_ledger(
            order_id, customer, amount, order_date, method, "completed", "regular sale"
        )
        self._add_ledger(
            order_id,
            customer,
            amount,
            order_date,
            method,
            "completed",
            "duplicate entry - do not match twice",
        )
        settlement_id = self._add_settlement(
            order_id, amount, fee, tax, net, settle_date, utr, "processed"
        )

        bank_ref = f"NEFT/{utr}/RZPPAYOUT"
        bank_date = settle_date + timedelta(days=random.randint(0, 1))
        self._add_bank(
            bank_date, "RAZORPAY SOFTWARE PVT LTD PAYOUT", bank_ref, credit=net
        )

        self._add_gt(
            order_id,
            settlement_id,
            bank_ref,
            "matched",
            "duplicate_id",
            "ledger row entered twice; must match exactly once",
        )

    def ref_typo_event(self) -> None:
        # Bank reference_no carries a 1-2 char typo of the true UTR.
        order_id, amount, order_date, method, customer = self._new_order()
        settle_date = order_date + timedelta(days=random.randint(1, 2))
        fee, tax = calc_fee_tax(amount)
        net = amount - fee - tax
        utr = gen_utr(settle_date)
        typo_utr = make_typo(utr)

        self._add_ledger(
            order_id, customer, amount, order_date, method, "completed", "regular sale"
        )
        settlement_id = self._add_settlement(
            order_id, amount, fee, tax, net, settle_date, utr, "processed"
        )

        bank_ref = f"NEFT/{typo_utr}/RZPPAYOUT"
        bank_date = settle_date + timedelta(days=random.randint(0, 1))
        self._add_bank(
            bank_date, "RAZORPAY SOFTWARE PVT LTD PAYOUT", bank_ref, credit=net
        )

        self._add_gt(
            order_id,
            settlement_id,
            bank_ref,
            "matched",
            "ref_typo",
            f"typo of true UTR {utr} in bank reference_no",
        )

    def pending_event(self) -> None:
        # Order captured but not settled yet - must NOT be flagged as a break.
        order_id, amount, order_date, method, customer = self._new_order()
        self._add_ledger(
            order_id,
            customer,
            amount,
            order_date,
            method,
            "pending",
            "awaiting settlement",
        )
        self._add_gt(
            order_id, "", "", "pending", "pending", "no settlement/bank row yet"
        )

    def chargeback_event(self) -> None:
        # Negative settlement entry reversing a completed order, plus a bank debit.
        order_id, amount, order_date, method, customer = self._new_order()
        reverse_date = order_date + timedelta(days=random.randint(5, 10))
        utr = gen_utr(reverse_date)

        self._add_ledger(
            order_id,
            customer,
            amount,
            order_date,
            method,
            "completed",
            "regular sale (later disputed)",
        )
        settlement_id = self._add_settlement(
            order_id,
            -amount,
            Decimal("0.00"),
            Decimal("0.00"),
            -amount,
            reverse_date,
            utr,
            "chargeback",
        )

        bank_ref = f"REV/{utr}/CHARGEBACK"
        bank_date = reverse_date + timedelta(days=random.randint(0, 1))
        self._add_bank(
            bank_date, "RAZORPAY CHARGEBACK REVERSAL", bank_ref, debit=amount
        )

        self._add_gt(
            order_id,
            settlement_id,
            bank_ref,
            "exception",
            "chargeback",
            f"chargeback reversal of Rs {money(amount)}",
        )

    def bundled_event(self) -> None:
        # 3 orders settled in one payout: settlements share the payout UTR and the
        # bank sees a single credit for the summed net amount.
        orders = [self._new_order() for _ in range(BUNDLE_SIZE)]
        settle_date = max(o[2] for o in orders) + timedelta(days=1)
        payout_utr = gen_utr(settle_date)

        total_net = Decimal("0.00")
        settlement_ids = []
        for order_id, amount, order_date, method, customer in orders:
            fee, tax = calc_fee_tax(amount)
            net = amount - fee - tax
            total_net += net
            self._add_ledger(
                order_id,
                customer,
                amount,
                order_date,
                method,
                "completed",
                "regular sale (bundled payout)",
            )
            settlement_ids.append(
                self._add_settlement(
                    order_id,
                    amount,
                    fee,
                    tax,
                    net,
                    settle_date,
                    payout_utr,
                    "processed",
                )
            )

        bank_ref = f"NEFT/{payout_utr}/RZPPAYOUT"
        bank_date = settle_date + timedelta(days=random.randint(0, 1))
        self._add_bank(
            bank_date,
            "RAZORPAY SOFTWARE PVT LTD BUNDLE PAYOUT",
            bank_ref,
            credit=total_net,
        )

        for order_id, settlement_id in zip((o[0] for o in orders), settlement_ids):
            self._add_gt(
                order_id,
                settlement_id,
                bank_ref,
                "matched",
                "bundled_match",
                f"bundled payout {payout_utr} covering {BUNDLE_SIZE} orders",
            )

    # ------------------------------------------------------------------ output

    def finalize(self) -> None:
        """Sort bank rows chronologically and recompute the running balance."""
        self.bank_rows.sort(key=lambda r: (r["date"], r["reference_no"]))
        balance = OPENING_BALANCE
        for row in self.bank_rows:
            balance += Decimal(row["credit"]) - Decimal(row["debit"])
            row["balance"] = money(balance)

    def summary_lines(self) -> list[str]:
        label_counts: dict[str, int] = {}
        for row in self.gt_rows:
            label_counts[row["edge_case_label"]] = (
                label_counts.get(row["edge_case_label"], 0) + 1
            )
        lines = [
            f"ledger rows:     {len(self.ledger_rows)}",
            f"settlement rows: {len(self.settlement_rows)}",
            f"bank rows:       {len(self.bank_rows)}",
            f"ground truth:    {len(self.gt_rows)} events",
            "",
            "edge-case distribution:",
        ]
        for label in sorted(label_counts):
            lines.append(f"  {label:<16} {label_counts[label]}")
        return lines


def generate(count: int, edge_cases: bool, seed: int) -> SyntheticGenerator:
    gen = SyntheticGenerator(seed=seed)
    for _ in range(count):
        gen.clean_event()
    if edge_cases:
        for _ in range(EDGE_CASE_COUNTS["bundled_match"]):
            gen.bundled_event()
        for _ in range(EDGE_CASE_COUNTS["partial_refund"]):
            gen.partial_refund_event()
        for _ in range(EDGE_CASE_COUNTS["rounding_diff"]):
            gen.rounding_diff_event()
        for _ in range(EDGE_CASE_COUNTS["duplicate_id"]):
            gen.duplicate_id_event()
        for _ in range(EDGE_CASE_COUNTS["date_drift"]):
            gen.date_drift_event()
        for _ in range(EDGE_CASE_COUNTS["ref_typo"]):
            gen.ref_typo_event()
        for _ in range(EDGE_CASE_COUNTS["pending"]):
            gen.pending_event()
        for _ in range(EDGE_CASE_COUNTS["chargeback"]):
            gen.chargeback_event()
    gen.finalize()
    return gen


def write_csv(path: Path, columns: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate ReconLoop synthetic data batch."
    )
    parser.add_argument(
        "--count", type=int, default=60, help="number of clean transactions"
    )
    parser.add_argument("--output", default="data/samples", help="output directory")
    parser.add_argument(
        "--seed", type=int, default=42, help="RNG seed for reproducibility"
    )
    parser.add_argument(
        "--edge-cases",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="inject labeled edge cases (default: on)",
    )
    args = parser.parse_args(argv)

    if args.count < 1:
        parser.error("--count must be >= 1")

    gen = generate(count=args.count, edge_cases=args.edge_cases, seed=args.seed)

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / "internal_ledger.csv", LEDGER_COLUMNS, gen.ledger_rows)
    write_csv(
        out_dir / "gateway_settlement.csv", SETTLEMENT_COLUMNS, gen.settlement_rows
    )
    write_csv(out_dir / "bank_statement.csv", BANK_COLUMNS, gen.bank_rows)
    write_csv(out_dir / "ground_truth.csv", GROUND_TRUTH_COLUMNS, gen.gt_rows)

    print(
        f"Wrote 4 files to {out_dir} (seed={args.seed}, edge_cases={args.edge_cases})"
    )
    print("\n".join(gen.summary_lines()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
