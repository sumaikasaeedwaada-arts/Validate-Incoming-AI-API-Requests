# Customer and Task Search Report

## Project structure and existing data

The active application is `AI_service.api:app`, a FastAPI application backed by
SQLite. Its relevant modules are:

- `AI_service/api.py` — routes, authentication dependencies, and API error
  handling.
- `AI_service/database.py` — SQLite schema, connections, and transaction
  management.
- `AI_service/dependencies.py` — bearer-token authentication and ownership
  checks.
- `AI_service/customer_context.py` — retrieval of customer-related excerpts
  from the caller's uploaded files.
- `AI_service/schemas/chat.py` — request-supplied `TaskContext`.
- `AI_service/static/` — the existing chat UI.

The current database has users, conversations, messages, uploaded documents,
and document chunks. It has **no normalized customer or task tables**.
Customer-related information is only present in user-owned uploaded document
text. Task fields (`task_id`, `current_task`, `details`, `status`, and `notes`)
are optional chat request context and are not saved as task records. The
existing UI has chat context inputs but no dedicated customer/task search
interface.

## Implementation

The new authenticated endpoints search the existing `documents` and `chunks`
tables for substring matches in the caller's ready documents:

- `GET /api/customers/search?q=ahmed`
- `GET /api/tasks/search?q=report`

Both use the same search service and return **document excerpts**, not
structured customer or task entities. A document can be returned from either
endpoint if its text matches the query. Results contain one excerpt per
document even if several chunks match. Excerpts are limited to 320 characters
and include the matched text with nearby context.

The response contains `success`, `results`, `total`, `limit`, and `offset`.
Each result contains `kind: "document_excerpt"`, `document_id`, `filename`,
`page_number`, and `snippet`. No customer record fields are synthesized.

`q` is required, trimmed, and limited to 200 characters. Blank values, invalid
query lengths, and invalid pagination parameters receive HTTP 422 responses.
Pagination defaults to 20 results, accepts limits from 1 to 50, and offsets
from 0 to 100000. No matching documents return HTTP 200 with an empty result
list. Database errors are logged and returned as a sanitized HTTP 503 response.

### Example requests

```text
GET /api/customers/search?q=ahmed&limit=20&offset=0
GET /api/tasks/search?q=monthly%20report&limit=20&offset=0
```

Send a valid bearer token in the `Authorization` header. The response shape
below is illustrative only; placeholder text is not a real record:

```json
{
  "success": true,
  "results": [
    {
      "kind": "document_excerpt",
      "document_id": "<document-id>",
      "filename": "<uploaded-file>",
      "page_number": 1,
      "snippet": "...<matching uploaded text>..."
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

No matches return:

```json
{
  "success": true,
  "results": [],
  "total": 0,
  "limit": 20,
  "offset": 0
}
```

## Query and security measures

- Every query is parameterized; text is evaluated inside SQLite and is never
  interpolated into SQL.
- A per-connection SQLite `casefold` function provides Unicode-aware
  case-insensitive substring matching.
- SQL filters documents by the authenticated user's ID and ready status before
  returning any excerpts. Existing ownership authentication is enforced by
  `authenticated_user`.
- Only one short excerpt per matching document is returned. Total matching
  documents are counted in SQL, and result rows are paginated in SQL rather
  than loading all document text into application memory.
- Existing indexes include `documents_user_created` and `chunks_document`.
  No new index was added: ordinary B-tree indexes cannot accelerate a
  case-folded arbitrary substring search. The current implementation scans
  eligible text in SQLite; a very large corpus may warrant a synchronized
  full-text index or search service.
- The chat frontend has no search-results interface, so no unrelated UI was
  introduced. The APIs are available in the FastAPI OpenAPI documentation.

## Files changed

- `AI_service/api.py` — authenticated customer/task search routes and
  sanitized database error handling.
- `AI_service/schemas/search.py` — typed response models.
- `AI_service/services/document_search_service.py` — user-scoped SQLite search,
  per-document de-duplication, and short excerpt generation.
- `AI_service/test_search_api.py` — endpoint and security tests using a
  temporary SQLite database.
- `README.md` — API list, data-source limitations, and test command.
- `CUSTOMER_TASK_SEARCH_REPORT.md` — this report.

## Tests and verification

Executed from the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s . -p 'test_*.py' -v
```

**Result: 123 tests passed** (`Ran 123 tests ... OK`). This includes ten
customer/task search API tests for full and partial customer details, email,
phone, company, task title/description/assignee/status/priority text, Unicode
case-insensitivity, no matches, pagination/de-duplication, authorization and
user isolation, invalid queries, excerpt limits, and database errors. Test
records are inserted only into temporary test databases.

Pylance syntax checks reported no syntax errors in the new Python modules.
Pylance Problems found no errors in the changed Python files, and `git diff
--check` completed without errors.

The default database file (`data/assistant.db`) was not present, and no
`DATABASE_PATH` override was configured in this workspace. Therefore the
endpoints were verified against temporary SQLite test data, but could not be
tested against pre-existing live customer/task documents in this checkout.

## Limitations and run commands

- These endpoints search uploaded document text; they do not return
  authoritative customer or task records.
- A text match does not establish that a document describes a customer or
  task. Task assignee, status, and priority are searchable only when those
  words occur in uploaded text; they are not structured filters.
- The application has no dedicated dynamic customer/task search UI. Frontend
  loading, empty-state, and overlapping-request behavior are therefore not
  applicable to this backend-only change.
- A true entity-search implementation requires normalized customer/task data
  and a defined import or persistence source.

Start the application from the repository root with:

```powershell
uvicorn AI_service.api:app --reload --env-file .env
```

Run all tests with:

```powershell
python -m unittest discover -s . -p 'test_*.py' -v
```
