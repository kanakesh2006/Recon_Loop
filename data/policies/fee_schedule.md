# Razorpay-Style Fee Schedule

Razorpay's standard payment gateway fee model used by ReconLoop's synthetic data:

- **Transaction fee:** 2% of the gross transaction amount, plus a flat ₹3 per transaction.
- **GST on fee:** 18% GST is charged on the fee itself (not on the transaction amount).
- **Net settlement:** `net_amount = gross_amount - fee - tax_on_fee`. The bank receives the net amount, not the gross.

## Worked example

For a ₹2,499.00 order:

- fee = 2% × 2499 + 3 = ₹52.98
- tax_on_fee = 18% × 52.98 = ₹9.54
- net_amount = 2499 - 52.98 - 9.54 = ₹2436.48

## Reconciliation implications

- The internal ledger records the GROSS amount (what the customer paid).
- The settlement record and the bank credit carry the NET amount.
- A ledger-vs-settlement amount difference of roughly 2% + ₹3 + GST is **expected and normal**, not an exception.
- Small rounding differences of ₹0.01–₹2.00 between expected and actual net amounts are typical fee/tax rounding artifacts and should be tolerated by amount-tolerance matching.
