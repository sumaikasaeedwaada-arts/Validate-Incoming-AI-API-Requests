# Customer Insights Implementation Report

## Architecture and data-source review

HisabDo-AI is a FastAPI application backed by SQLite. Authentication uses
signed bearer tokens, and the API's existing `authenticated_user` dependency
resolves the caller before authenticated routes access data. Uploaded documents
are owned by `documents.user_id`; their extracted text is stored in `chunks`.
The existing RAG service retrieves those chunks for chat and customer-context
lookups. Gemini calls are made through the existing `ai_service` adapter.

The database schema currently contains `users`, `conversations`, `messages`,
`documents`, `chunks`, vector-index state, and rate-limit buckets. It does not
contain normalized customer, support-ticket, feedback, transaction, or
customer-interaction tables. Conversation messages are AI chat history, not a
structured record of customer interactions. The implementation therefore does
not invent tables or treat those messages as operational customer evidence.

## Data sources used

- Ready document chunks joined to their owning `documents` rows.
- Owner restriction: `documents.user_id` must equal the authenticated user ID.
- Optional date filters apply to document `created_at` upload timestamps.
- Optional customer identifier is matched against chunk text.
- No other user's documents or global cross-tenant records are queried.

The analysis does not assert that a document describes a particular customer
unless the optional identifier filter is supplied and found in that text.
Documents without structured event dates cannot support a reliable event trend;
reported dates are identified as document upload timestamps.

## Implementation

- `AI_service/schemas/customer_insights.py`: validated date and identifier
  request fields, constrained insight items, and structured response schema.
- `AI_service/services/customer_insights_service.py`: scoped retrieval,
  bounded text processing, overlap-aware chunk reconstruction, keyword-based
  measurement, minimum recurrence threshold, explicit limitations, and
  evidence-constrained service-opportunity generation via the existing Gemini
  adapter.
- `AI_service/api.py`: authenticated `POST /api/customer-insights` endpoint
  with sanitized 502, 503, and 500 responses.
- `AI_service/test_customer_insights.py`: API and service behavior tests using
  an isolated temporary SQLite database and mocked model calls.
- `README.md`: endpoint and data-scope documentation.

The retrieval and evidence passed to the LLM are limited to aggregate topic
counts. Raw customer document text, identifiers, contact details, account
information, and transaction details are not sent as opportunity-generation
context. The service distinguishes measured categories and counts from
AI-generated recommendations using the `basis` field.

## Insight-generation workflow

1. FastAPI validates the request and resolves the caller through the existing
   bearer-token dependency.
2. The service selects ready chunks belonging only to that caller, applies
   supported upload-date and identifier filters, and caps processing at 500
   chunks / 100,000 characters.
3. Contiguous chunks from each document are reconstructed to avoid counting
   repeated text caused by chunk overlap.
4. Document text is checked against explicit issue, interaction, feedback, and
   transaction phrase categories.
5. A category is reported only when matching phrases appear in at least two
   distinct documents. Counts mean matching text mentions and distinct
   documents; they are not counts of unique customers, verified cases, or
   completed transactions.
6. Only measured issue and feedback topics with supporting counts are provided
   to Gemini for cautious service-opportunity interpretation. Each returned
   opportunity must cite a measured topic; unsupported topics are rejected.
7. Missing sources, insufficient evidence, truncation, and upload-date
   limitations are included in `data_limitations`. No-data results return
   empty insight arrays rather than fabricated findings.

## API

`POST /api/customer-insights` requires the existing bearer authentication.

Example request:

```json
{
  "date_from": "2026-10-01",
  "date_to": "2026-10-27",
  "customer_identifier": "C-104"
}
```

Example response shape (illustrative structure, not a claim about live
customer records):

```json
{
  "success": true,
  "insights": {
    "frequently_reported_issues": [],
    "interaction_patterns": [],
    "feedback_themes": [],
    "transaction_patterns": [],
    "service_opportunities": [],
    "data_limitations": [
      "The database has no normalized customer, interaction, support-ticket, feedback, or transaction tables; analysis uses user-owned uploaded document text only.",
      "Dates refer to document upload timestamps, not necessarily the dates of customer events described in those documents.",
      "No recurring issue was detected from the available text; this does not establish that customers reported no issues."
    ]
  }
}
```

When evidence exists, each measured category includes `occurrence_count`,
`distinct_document_count`, `first_record_upload`, and `last_record_upload`.
AI-generated service opportunities include an evidence topic, its supporting
document count, and `basis: "AI interpretation"`.

## Privacy and access control

- Uses the existing authentication dependency; unauthenticated calls receive
  HTTP 401.
- Every record query is scoped to the authenticated user's document ownership.
- Uses parameterized SQL for user ID, dates, and customer identifier.
- Does not log customer text or identifiers; error logs use generic messages.
- Limits LLM input to aggregate measurements and validates model output against
  those measurements.
- Returns generic client-facing messages for database and AI failures.

The application has account-level document ownership, not a separate business
or tenant model. Accordingly, no unsupported business filter is exposed.

## Tests and verification

Executed:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest AI_service.test_customer_insights AI_service.test_business_summary
```

Result: **18 tests passed** (9 Customer Insights tests and 9 existing Business
Summary regression tests). The customer-insights tests exercise temporary
SQLite-backed retrieval, repeated issue and feedback detection, interaction
and transaction wording, mention/document counts, chunk-overlap handling,
customer/date filtering, empty data, single-record evidence, cross-user
isolation, authentication, invalid model output, and simulated AI/database
failures.

Model calls in these tests are mocked. These results do not represent a live
Gemini integration test or an analysis of production customer records.

Additional verification:

- Pylance reported no errors in the new schema, service, endpoint, or tests.
- `git diff --check` completed successfully.
- An authenticated local `POST /api/customer-insights` request with a temporary
  account and empty temporary database returned HTTP 200 with empty insight
  arrays and explicit data limitations. This verifies the live local HTTP
  route, not a live Gemini call or production data analysis.
- A screenshot file was not saved; automated validation used FastAPI's
  in-process `TestClient`, and the local HTTP check was verified from its JSON
  response.

## Limitations and recommended improvements

- Insights are based on uploaded text rather than normalized customer activity,
  ticket, feedback, or transaction records.
- Keyword matching is intentionally conservative and may miss synonyms,
  negation, or context; matched text still requires human interpretation.
- A two-document threshold prevents single-document anecdotes from becoming
  recurring findings, but does not establish statistical significance or
  distinct-customer prevalence.
- Upload times cannot be substituted for event times; robust trend reporting
  requires source event timestamps.
- Transaction phrases are not a ledger and cannot establish amounts, payment
  status, frequency per customer, or revenue trends.
- To improve coverage, add appropriately authorized structured source systems
  or typed records with event dates and stable pseudonymous customer keys, then
  extend aggregation and retention controls with tests before introducing
  customer-level trend claims.

## Run commands

From the repository root:

```powershell
& '.\.venv\Scripts\python.exe' -m uvicorn AI_service.api:app --reload
```

Run focused tests:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest AI_service.test_customer_insights AI_service.test_business_summary
```
