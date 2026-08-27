# Deduction-stack primer (one page)

A settlement credit is a **net**. Gross captured payments, minus refunds and chargebacks,
plus representments, minus the aggregator's platform fee, minus GST on that fee, minus
withholding on gross (section 194-O at 10 bps in this synthetic merchant), minus a rolling
reserve hold, plus reserve releases, minus a bank transfer charge.

Every amount is integer paise. Rounding is half-up, once per derived line, never on a total.

You get the same three rendered views the system gets: settlement report, internal ledger,
bank statement. Name the member set if you can (`CLEARED`), flag if you need more information
(`FLAGGED`), or stop if you cannot finish (`GAVE_UP`).

Do not discuss cases with other raters until every sheet is sealed.
