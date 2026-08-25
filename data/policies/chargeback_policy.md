# Chargeback & Reversal Policy

A chargeback (dispute) reverses a previously settled payment.

## How chargebacks appear in the data

- The settlement feed contains a **negative net_amount** entry with `status="chargeback"` and `txn_type="chargeback"`, referencing the original order via `txn_ref`.
- The bank statement shows a corresponding **debit** (money leaving the account) whose reference contains the reversal UTR, typically formatted `REV/{utr}/CHARGEBACK`.
- The internal ledger keeps the original completed order row; it does not automatically record the reversal.

## Why chargeback orders land in the exception queue

The original ledger order (a completed payment) has a settlement record of type `chargeback` rather than a normal settlement, so the ledger↔settlement exact match correctly refuses to pair them. The chargeback settlement and the bank debit DO pair with each other (matched by UTR and amount). The ledger order itself remains unresolved and is flagged as an exception — this is **intentional and correct behavior**: a chargeback is a genuine break in the books that a human must confirm.

## Suggested resolution

1. Confirm the dispute in the gateway dashboard.
2. Record a chargeback entry in the internal ledger referencing the original order.
3. If the dispute is won, expect a compensating credit in a later settlement batch.
