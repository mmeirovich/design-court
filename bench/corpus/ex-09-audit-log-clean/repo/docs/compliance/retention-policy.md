# Records retention policy

Version 3, effective 2026-01-01. Owner: Compliance. Changes need Compliance sign-off.

## Control requirements for audit records

- **AU-2 Completeness.** A privileged administrative action may not take effect unless the
  audit record for it is committed with it.
- **AU-3 Content.** Each record identifies who acted, when, what they did, on which object,
  and from which network address.
- **AU-9 Protection.** Audit records may not be modified or deleted by the people whose
  actions they record. Only Security and Compliance staff may read them. Reading the
  records is itself recorded.
- **AU-11 Retention.** See the table below.

## Retention periods

| Record class | Retain | Delete within | Notes |
|---|---|---|---|
| Application logs | 30 days | 7 days after expiry | |
| Admin audit records (privileged administrative actions) | 400 days from the event time | 60 days after expiry | A legal hold suspends deletion until it is released. |
| Billing records | 7 years | 90 days after expiry | |

## Copies

Copies of a record in downstream systems (exports, search indexes, backups) must be gone no
later than 60 days after the record's own expiry. Database backups are kept for 35 days and
are not rewritten to remove individual records.
