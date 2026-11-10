# Customer Insights and Sensitive Information Security Audit

## 1. Project architecture reviewed

The deployed application entry point in `Dockerfile` is `AI_service.api:app`.
The active API is a FastAPI application backed by SQLite. Its existing
architecture includes:

- `AI_service/api.py` for routes, authentication dependencies, and sanitized
  API errors.
- `AI_service/database.py` for the SQLite schema and connections.
- `AI_service/dependencies.py` and `AI_service/security.py` for bearer-token
  authentication and ownership checks.
- `AI_service/services/` for chat, retrieval, business summaries, and customer
  insights.
- `AI_service/context/`, `AI_service/rag.py`, and `AI_service/customer_context.py`
  for AI instructions and user-scoped document retrieval.
- `AI_service/static/` for the existing business summary and insights UI.

The database schema contains users, conversations, messages, uploaded
documents, extracted document chunks, vector-index state, notifications, and
rate-limit buckets. It does not contain normalized customer, business,
support-request, feedback, or transaction tables.

## 2. Customer data sources

The existing insights service reads ready document chunks joined to documents
owned by the authenticated user. Optional date filters refer to document
upload timestamps; an optional customer identifier filters document text.
Conversation history is not treated as an operational customer interaction
record. No other user's documents are used.

The configured default database `data/assistant.db` was absent in this
checkout. Therefore there were no existing customer records available for a
live data analysis. Automated tests use isolated temporary SQLite databases
and controlled test fixtures; those fixtures are not real customer activity.

## 3. Customer Insights implementation

The existing feature was retained and tightened without introducing duplicate
modules or unsupported database tables:

- Counts issue, interaction, feedback, and transaction-related text patterns
from available uploaded documents.
- Reconstructs contiguous chunks to reduce overlap-related overcounting and
  excludes exact duplicate documents.
- Requires a pattern to occur in at least two distinct documents.
- Caps processing at 500 chunks and 100,000 characters.
- Reports limitations and keeps document upload dates distinct from event
  dates.
- Now explicitly states that total, active, inactive, and unique customer
  counts cannot be calculated from this schema. App accounts and text mentions
  are not treated as customer records.
- Returns empty findings instead of unsupported conclusions when evidence is
  missing or below threshold.

These are document-text indicators, not verified support cases, unique
customers, ledger entries, or statistically significant trends.

## 4. Customer activity analysis

Supported measures include keyword occurrences and the number and upload-date
range of distinct matching documents. Repeated support-contact wording,
follow-ups, issue phrases, feedback themes, and transaction-related wording
are measured where present.

The database cannot supply registered customer totals, active/inactive status,
structured interaction histories, support resolution/performance metrics,
customer-level recurrence, or authoritative transaction counts. Those
measurements are identified as unavailable, not inferred from unrelated
application users or chat messages.

## 5. AI model integration

The feature reuses the configured Gemini adapter via
`AI_service.ai_service.generate_answer`. The model is used only to suggest
cautious service opportunities from measured issue/feedback categories and
distinct-document counts. Raw document text, identifiers, customer contact
details, and financial details are not included in this prompt. The returned
model output is validated against supplied evidence; unsupported topics and
malformed responses are rejected.

Automated tests mock the model. A live Gemini/provider call was not made, so
provider connectivity and live-model quality were not verified.

## 6. API endpoints

- `POST /api/customer-insights` returns authenticated customer insights.
- `POST /api/business/insights/generate` reuses the same user-scoped analysis
  and is used by the existing insights UI.

Both require the existing authenticated-user dependency. AI, database, and
invalid-model-output failures map to generic 503, 500, and 502 responses.

## 7. Security vulnerabilities identified

The delegated security review reported **no substantiated vulnerabilities**
in its reviewed active API scope: authentication/authorization, per-user
document and conversation/notification isolation, customer/financial data
handling, SQL construction, AI prompt/context handling, frontend rendering,
logs/errors, and secret configuration.

No confirmed security vulnerability was identified or represented as fixed
by this change. The review does not certify third-party provider behavior,
deployment infrastructure, or a live production configuration.

## 8. Security fixes implemented

No security vulnerabilities were identified by the review requiring a
security patch. This change strengthens the existing data-accuracy boundary
by explicitly disclosing unsupported customer totals and adds regression
coverage demonstrating that customer identifiers, email-like values, and
prompt-injection text in documents are not sent to the opportunity model or
returned in the insight response.

Existing authentication, owner-scoped SQL retrieval, aggregate-only model
prompting, model-output validation, and generic error responses were retained.

## 9. Authentication and authorization testing

The customer-insights tests verify successful authenticated requests,
unauthenticated requests, invalid bearer tokens, and the authenticated business
insights route. The broader suite also exercises registration/login, token
validation, protected routes, and conversation/document access behavior.

## 10. Business data isolation testing

Insights retrieval filters documents by the authenticated `user_id`. Tests
insert records belonging to another user and confirm they do not affect counts
or model input. The existing schema provides account-level ownership, not a
separate business/tenant identifier. Accordingly, isolation is verified
between accounts; separate businesses managed by one account cannot currently
be isolated from each other using this schema.

## 11. Files created or modified

- Created `CUSTOMER_INSIGHTS_SECURITY_AUDIT_REPORT.md` (this report).
- Modified `AI_service/services/customer_insights_service.py` to disclose
  unavailable customer counts instead of implying they can be measured.
- Modified `AI_service/test_customer_insights.py` with explicit customer-count,
  prompt-injection/sensitive-text, and invalid-token assertions.

Other reviewed components include the active API, authentication/dependency
helpers, database schema, AI adapter, document/customer context retrieval,
chat prompt construction, Docker entry point, and existing customer-insights
UI.

## 12. Automated test cases

The customer-insights tests cover:

- Retrieval from user-owned documents; cross-user isolation.
- Issue, interaction, feedback, and transaction wording patterns.
- Occurrence and distinct-document counts, duplicate exclusion, and chunk
  overlap.
- Customer identifier and upload-date filters.
- Empty data and explicit missing-customer-statistics limitations.
- Sensitive document text and prompt-injection content excluded from model
  input and the API response.
- Valid, missing, and invalid authentication.
- AI provider failure, invalid model output, and database failure handling.

The full backend suite additionally covers authentication, chat, document
retrieval, business summaries, communications, notifications, search, and
other API regressions.

## 13. Actual test results

Executed after the changes:

```powershell
.\.venv\Scripts\python.exe -m unittest AI_service.test_customer_insights
```

Result: **13 tests passed**.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s AI_service -p 'test_*.py'
```

Result: **95 tests passed** (`Ran 95 tests in 42.192s`, `OK`).

`git diff --check` completed successfully. The suite emitted an existing
Starlette/httpx deprecation warning; it did not fail the tests. Model/provider
failure log lines in the suite are generated by tests that intentionally
exercise error handling.

The FastAPI application and endpoints were exercised in-process through
`TestClient`, including empty-data, authenticated, unauthorized, isolated-data,
and mocked-model cases. No production/default database was present, no live
Gemini call was made, and no screenshot of real customer analysis was
captured.

## 14. Remaining issues and recommendations

- Add normalized customer, interaction, support-ticket, feedback, and
  transaction records before reporting true customer totals, customer
  activity/status, service performance, or financial metrics.
- Store event timestamps and explicit customer/business ownership so trends
  and customer-level recurrence can be measured accurately.
- If an account can contain multiple businesses, introduce and consistently
  enforce a business/tenant ID across document ingestion, retrieval, chat,
  and insights; the current model isolates by account only.
- Treat keyword-derived themes as indicators for human review; consider
  evaluating classification quality against curated, authorized operational
  records before using them for decisions.
- Re-run an authorized live-data check and live provider integration test in
  the target deployment after supplying its database and secrets through the
  normal deployment configuration. Do not use copied or fabricated customer
  records for that verification.
