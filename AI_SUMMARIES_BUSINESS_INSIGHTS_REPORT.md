# AI Summaries and Business Insights Review

## Scope and evidence

This review covers the FastAPI application under `AI_service/`, its SQLite
schema, the existing Gemini integration, summary and customer-insights
services, API routes, and the browser workspace.

The configured local database file (`data/assistant.db`) and `.env` file were
not present. The application was therefore run against an isolated temporary
database for UI verification, and automated tests used temporary SQLite
databases containing test records. No production or live business records were
available for this review. A live Gemini generation was not performed; AI
calls were mocked in tests.

## 1. Existing project architecture

- `AI_service.api:app` is the active FastAPI application. The root-level
  modules are not the active package entry point.
- `AI_service.database` creates SQLite connections and initializes the
  schema. Relevant persisted entities are users, conversations, messages,
  uploaded documents, and document chunks.
- Documents are owned by `documents.user_id`. There is no separate business
  or tenant model and no normalized company-profile, customer, task,
  operational-activity, customer-interaction, or transaction tables.
- `AI_service.services.business_summary_service` builds summaries from
  caller-owned uploaded document chunks and optional request-provided business
  and task context.
- `AI_service.services.customer_insights_service` measures text patterns from
  caller-owned uploaded documents and optionally asks the existing AI model
  for evidence-constrained service-improvement opportunities.
- `AI_service.services.ai_model_service` provides the configured Gemini model
  through the existing `generate_answer` adapter. No model or provider was
  replaced.
- `AI_service/static/` contains the authenticated browser workspace.

## 2. Business Summary

The existing `POST /api/business-summary` path was retained and wired into
the workspace. The service:

1. Selects ready document chunks belonging to the authenticated user.
2. Applies optional inclusive date filters to document upload timestamps.
3. Includes up to five recent chunks and, when requested, up to five matching
   customer chunks.
4. Adds optional request-provided business/task context while marking it as
   unverified user input.
5. Uses the existing Gemini adapter when there is information to summarize.
6. Validates the model response against the strict `BusinessSummary` Pydantic
   schema and merges in known data limitations.
7. Returns an explicit no-information summary without calling the model when
   no source data or context is available.

The prompt asks for structured facts and updates, prohibits invented details,
and distinguishes document upload dates from event dates. The summary does
not claim authoritative customer/task totals because the database does not
store those records in structured form.

## 3. Business Insights

The existing customer-insights analyzer was reused instead of duplicating its
retrieval or aggregation logic. It is now also available as
`POST /api/business/insights/generate`, and the workspace includes a
generation/refresh action.

The analyzer:

- Scans at most 500 chunks / 100,000 characters for a request.
- Reconstructs contiguous chunks to avoid double-counting overlap.
- Deduplicates exact full-document text after whitespace and case
  normalization; when copies have different upload timestamps, the most
  recently uploaded copy is encountered first and retained.
- Measures configured issue, interaction, feedback, and transaction wording
  categories in Python.
- Reports a pattern only when matching text occurs in at least two distinct,
  non-duplicate documents.
- Reports mention counts, distinct-document counts, and first/last upload
  timestamps. Those counts are not unique-customer, verified-case, task, or
  ledger totals.
- Requests recommendations only for measured issue or feedback evidence. It
  validates that each AI recommendation names a measured topic and fills its
  supporting-document count from the computed evidence.
- Returns no recommendations when evidence is insufficient, and reports
  limitations instead of implying that unavailable information is zero.

Exact-content deduplication prevents repeated uploads of the same text from
creating a recurrence by themselves. Different documents cannot be proven to
represent separate customers or real-world events because the schema has no
record-level identity.

## 4. Database records and data sources

Data used:

- `documents`: caller ownership, ready status, filename, and upload timestamp.
- `chunks`: extracted text, chunk order, and page number.
- Optional `customer_identifier`, `business_context`, and `task_context`
  fields supplied in the authenticated request.

Data deliberately not treated as available:

- Structured company profile, customer count, task status/completion totals,
  operational activity, customer interaction history, and financial
  transactions.
- Conversation messages as customer activity; they are AI chat history.
- Document upload timestamps as dates of events described in the document.

Customer and business facts appearing in uploaded text are document evidence,
not normalized database records. Summary date ranges filter upload timestamps;
they cannot establish that an event occurred during that interval.

## 5. AI model and prompt integration

The existing `GEMINI_MODEL` and `GEMINI_TIMEOUT_MS` settings and
`ai_service.generate_answer` adapter are reused. The model setting defaults to
`gemini-3.5-flash-lite` when not overridden. The summary flow sends the
selected source chunks and request context with grounding, recency, privacy,
and missing-data instructions. The insights recommendation flow sends only
aggregate measured topics and counts, not raw customer document text.

Tests mock model calls, including provider timeouts and invalid responses.
Consequently, provider credentials are not logged or returned, but live
provider behavior was not verified in this run.

## 6. API endpoints

All feature endpoints require the existing bearer authentication.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/business-summary` | Generate a structured summary from the caller's uploaded records and optional user-provided context |
| POST | `/api/business/insights/generate` | Generate measured business/customer insights and supported recommendations |
| POST | `/api/customer-insights` | Existing compatible customer-insights route; retained |

Summary request fields include optional `date_from`, `date_to`,
`customer_identifier`, `business_context`, and `task_context`. The business
insights request accepts the date filters and optional customer identifier.
Dates are validated, and reversed ranges return HTTP 422.

The new business-insights route uses the existing `CustomerInsightsResponse`
shape, including measured issue, interaction, feedback, and transaction-text
categories, service opportunities, and data limitations. It is a generation
endpoint, not a persisted report store; no GET endpoint was added because the
application has no stored insight snapshots.

## 7. Data accuracy and validation

- SQL queries use parameterized values and filter on the authenticated user's
  `documents.user_id`.
- Python pattern matching computes occurrence and distinct-document counts;
  numeric calculations are not delegated to the model.
- Chunk overlap is reconstructed before matching; exact duplicate document
  text is excluded from counts.
- AI output is validated against strict schemas. Unsupported recommendation
  topics are rejected.
- Empty data produces empty findings and explanatory limitations; it does not
  turn missing records into zero-valued business claims.
- Date filters and reported periods refer to document upload times.
- A minimum of two distinct documents is an evidence threshold, not a claim
  of statistical significance.

## 8. Security and error handling

- Both APIs depend on the existing authenticated-user dependency.
- Database reads are scoped to that user; cross-user isolation is exercised by
  tests.
- Provider and database failures return sanitized API errors. Provider
  details, prompts, and private text are not included in service error logs.
- AI recommendations receive aggregates rather than raw customer text.
- Summary generation uses selected source text with explicit instructions to
  avoid unnecessary customer identifiers and contact details.
- Existing rate limiting applies to the new route because it is under `/api/`.
- The schema has user-level, not business-level, isolation. A supplied
  `business_id` cannot be used to establish or filter business ownership.

## 9. Files changed

- `AI_service/api.py` — added the authenticated business-insights generation
  route and reused existing error handling.
- `AI_service/services/customer_insights_service.py` — excluded exact
  duplicate document text and reported the exclusion.
- `AI_service/test_customer_insights.py` — added route, isolation, and
  duplicate-document regression coverage; made repeated-record fixtures
  distinguishable.
- `AI_service/static/index.html` — added business report controls, date
  filters, and a report output region.
- `AI_service/static/app.js` — connected summary/insight actions; added
  loading, success, empty, and error rendering using text nodes.
- `AI_service/static/styles.css` — styled report controls and results,
  including a narrow-screen layout.
- `README.md` — documented the new endpoint and the limits of available
  business data.
- `AI_SUMMARIES_BUSINESS_INSIGHTS_REPORT.md` — this review report.

## 10. Tests and actual results

Executed:

```powershell
& '.\.venv\Scripts\python.exe' -m unittest AI_service.test_business_summary AI_service.test_customer_insights AI_service.test_chat_api AI_service.test_rag_api
```

Result: **69 tests passed** (`Ran 69 tests in 16.330s`, `OK`). The run includes
summary grounding, missing data, date filters, customer matching,
authentication, data isolation, model/database failures, invalid model
output, measured insight counts, evidence thresholds, recommendations, chunk
overlap, exact duplicate-document suppression, and chat/retrieval regressions.
The test runner emitted a Starlette/httpx `TestClient` deprecation warning.

Also executed successfully:

- `python -m py_compile` on changed Python source and test files.
- `node --check AI_service\static\app.js`.
- `git diff --check`.
- Uvicorn on `127.0.0.1:8765` with an isolated temporary database. An
  authenticated browser session generated the empty-data summary and insights
  successfully (HTTP 200 for both); the responses showed empty states and
  data limitations without requiring a model call.
- Browser UI verification confirmed the loading/disabled state and a readable
  error message for a mocked 503. At a 390px viewport, the report section
  measured 320px wide with a 320px scroll width. No JavaScript console errors
  were recorded during the successful summary/insights flow.
- A browser screenshot of the report interface was captured during that
  verification.

Automated tests used fixture database rows and mocked AI responses; the browser
run used an empty temporary database. No live business records were available
for direct verification and no live Gemini request was made.

## 11. Bugs and gaps addressed

- There was no business summary or insights generation interface in the
  browser, despite existing API functionality. Added controls and visible
  result, loading, empty, and error states.
- Insights were exposed only through a customer-named route. Added a
  business-insights generation route while retaining the existing endpoint
  and response shape.
- Exact duplicate uploaded text could previously count as multiple documents
  and satisfy the recurrence threshold. Duplicate text is now excluded, with
  the exclusion disclosed in limitations.

## 12. Remaining issues and limitations

- The local configured business database was absent. Running against actual
  customer records, tasks, operational events, or transactions remains
  unverified.
- Implementing authoritative business totals, task-completion metrics,
  transaction totals, and real activity trends requires normalized,
  business-attributed tables with stable record IDs and event timestamps.
- Current issue and interaction categorization is keyword-based; it can miss
  synonyms, negation, or context. Its mention counts are not verified cases.
- Duplicate detection is exact full-text normalization only. Similar but
  non-identical duplicate records cannot be reliably identified without
  record-level IDs.
- Upload times cannot be used as event times. Summary prompt selection is
  bounded to recent chunks, so older relevant details may not be included.
- Live Gemini latency, response quality, quota behavior, and provider-side
  privacy configuration were not tested.
- There is no persisted insight history or GET endpoint for previously
  generated reports.
