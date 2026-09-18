# Error reporting implementation plan

Approved scope: user-reviewed diagnostic reports, Workers + private R2, no deployment credential in the app. This is a new subsystem; the design and abuse limits were approved in chat.

## Design

The app retains a bounded structured diagnostic journal: error codes, exception classes and application stack locations, never exception text, engine output, OCR text, document names, account names or paths. Reports include system specifications and aggregate job states. Optional contact/reproduction text is explicitly user-supplied. A frozen preview expires after 15 minutes; submission sends exactly that preview. Download remains available if submission fails. No automatic reporting.

Workers accepts JSON <=256 KiB, validates the schema, applies IP rate limits, then reserves a slot through one SQLite Durable Object before one R2 write. A single transactional global counter allows 1,000 reservations per UTC day, including failed writes. Failure of any guard fails closed. R2 has no public reads; lifecycle expires reports after 30 days. Workers remains on Free. These are application limits, not an account-wide billing guarantee; other account usage still counts. Report floods can deny availability, so the client offers file export.

## Work

- [x] Add failing privacy, frozen-preview, origin and submission tests; implement app/diagnostics.py and router.
- [x] Wire structured error collection into API/worker; implement shared accessible report dialog and browser tests.
- [x] Add Worker validation, quota and failure tests; implement receiver and deployment/admin tooling.
- [x] Verify targeted and regression tests, deploy receiver with synthetic-only smoke data, verify private storage/lifecycle, configure public endpoint.
- [x] Document operator retrieval and limitations. Review diff and report implementation/release status accurately.

Verification: 174 regression tests passed before the final progress schema addition; all 9 diagnostic API/browser tests passed after it. Six receiver tests passed. Production synthetic smoke passed (acceptance, schema/size/rate guards, denied public reads); authenticated report retrieval and private bucket/30-day lifecycle verified. Source preview restarted on port 8001. No new EXE release created in this task.
