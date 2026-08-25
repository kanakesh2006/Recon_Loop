# Settlement Delays & Bundled Payouts

Money does not always move the day an order is placed.

## Normal settlement lag

A captured order typically settles in **1–2 days**. The bank credit lands on the settlement date or up to 1 day later.

## Delayed settlements (date drift)

Settlements can be delayed by **3–5 days** (weekends, bank cut-off times, risk holds). ReconLoop's exact matcher allows up to 2 days of lag; anything beyond that falls to the fuzzy stage, which tolerates date drift up to the configured window when the order reference matches exactly.

## Bundled payouts

Gateways often pay out **multiple orders in a single payout**:

- Several settlement records share one payout UTR.
- The bank sees **one credit** equal to the sum of the settlement net amounts.
- Because payouts batch orders settled on different days, the lag between an individual order date and the payout date can reach **up to 30 days** for the earliest order in the bundle.

## Reconciliation implications

- A bank credit whose amount equals the SUM of several settlements sharing one UTR is a bundled payout, not a discrepancy.
- Large date gaps are acceptable when the order reference (order_id = txn_ref) matches exactly; the reference is the authoritative identifier, the date is informational.
