# HisabDo-AI — Overall Work Report

## 1. Project overview

HisabDo-AI is a Python application built around FastAPI, Pydantic, SQLite,
Gemini, and document-based retrieval. The primary application is
`AI_service.api:app`. It provides authenticated APIs for conversations,
document-backed assistance, summaries, customer insights, and generated
business communications.

The application reuses the configured Gemini model and shared AI service.
Authenticated data access is tied to the current user's account. Uploaded
documents are stored as chunks in SQLite and are retrieved within that user
scope. Public business information is retrieved separately from the prepared
business knowledge source.

## 2. Main capabilities covered in the project

### Authenticated chat and business context

- Bearer-token registration, login, and authenticated endpoints.
- Conversation creation, retrieval, and messages.
- Prompt composition using relevant user-owned document excerpts,
  conversation history, optional request-provided business/task context, and
  relevant prepared public business knowledge.
- Document ownership checks and citation-preserving chat responses.
- Prompt guidance to distinguish evidence from user-provided context, avoid
  unsupported claims, handle missing or conflicting facts, and treat retrieved
  records as information rather than instructions.

### Document RAG and retrieval

- PDF, DOCX, and TXT upload and text extraction.
- Text chunking and Gemini embeddings, with user-document vectors stored in
  SQLite.
- Similarity-based retrieval scoped to the authenticated user.
- Prepared public business knowledge retrieval with visibility controls,
  relevance filtering, metadata, and in-memory embedding cache.
- Validation and handling for malformed vectors and unavailable retrieval.

### Business summary

- Authenticated `POST /api/business-summary`.
- Uses the caller's ready uploaded document chunks and optional
  request-provided context; optional customer matching is limited to that
  user's records.
- Returns a structured summary with data limitations rather than inventing
  unavailable business, task, or customer data.
- Uses the existing Gemini integration and validates structured output.

### Customer insights

- Authenticated `POST /api/customer-insights`.
- Measures recurring issue, interaction, feedback, and transaction wording in
  ready documents owned by the caller.
- Supports optional upload-date and customer-identifier filters.
- Requires evidence across at least two distinct documents before reporting a
  recurring pattern and avoids counting repeated overlapping chunks as
  separate records.
- Sends aggregate measurements, rather than raw customer text, to the model
  for evidence-constrained service-opportunity suggestions.
- Clearly states that uploaded document dates are not necessarily customer
  event dates and that keyword counts do not represent unique customers or
  verified transactions.

### Email and message generation

- Authenticated `POST /api/communications/generate`.
- Generates a structured email (`subject`, `body`) or a concise message
  (`message`) using the existing Gemini service.
- Supports customer support, follow-up, reminder, announcement, business
  update, invitation, meeting confirmation, and custom purposes.
- Accepts recipient context, up to 20 key points (500 characters each), tone,
  length, language, optional customer identifier, sender name, and additional
  instructions.
- Uses relevant public business context and, only when requested, customer
  excerpts from the authenticated user's ready documents.
- Prompts against invented prices, dates, policies, commitments, and other
  unsupported facts. The endpoint generates content only; it does not send
  messages.

### Application behavior and operations

- Shared request validation through Pydantic schemas.
- API rate limiting and sanitized errors for authentication, validation,
  context retrieval, model failures, and malformed model output.
- Configuration through environment variables such as `GEMINI_API_KEY`,
  `GEMINI_MODEL`, `GEMINI_TIMEOUT_MS`, `AUTH_SECRET`, and `DATABASE_PATH`.
- README documentation for setup, API endpoints, configuration, and tests.

## 3. Current Git worktree inventory

The following paths were reported as modified or untracked in the worktree
when this overall report was prepared:

| Path | Worktree status | Summary |
|---|---|---|
| `AI_service/api.py` | Modified | Adds the authenticated customer-insights route; the communication and chat routes are also part of the existing application. |
| `AI_service/schemas/communication.py` | Modified | Adds key-point validation and additional communication purpose values. |
| `AI_service/services/communication_service.py` | Modified | Includes key points in context retrieval and the generation prompt. |
| `AI_service/test_communication.py` | Modified | Adds coverage for key-point constraints and additional purposes. |
| `AI_service/schemas/customer_insights.py` | Untracked | Customer-insights request, response, and validation models. |
| `AI_service/services/customer_insights_service.py` | Untracked | User-scoped document analysis and evidence-based insights. |
| `AI_service/test_customer_insights.py` | Untracked | Mocked API/service tests for customer insights and access boundaries. |
| `README.md` | Modified | Documents APIs and project usage, including customer insights and communications. |
| `CUSTOMER_INSIGHTS_REPORT.md` | Untracked | Customer-insights architecture, privacy, testing, and limitations report. |
| `EMAIL_MESSAGE_GENERATION_REPORT.md` | Modified | Final email/message generator implementation and verification report. |
| `chatbot_report_screenshot.png` | Deleted | A deletion is present in the worktree. It is not described as an intentional feature change in this report. |

This table describes the observed working-tree status, not a claim that every
listed file was created during the same implementation task. The screenshot
deletion is noted for review; this report does not restore or otherwise alter
it.

## 4. Related project reports

These reports contain deeper implementation details, test descriptions, and
known limitations for their individual areas:

- `EMAIL_MESSAGE_GENERATION_REPORT.md` — email and message generation.
- `CUSTOMER_INSIGHTS_REPORT.md` — customer insights.
- `BUSINESS_SUMMARY_REPORT.md` — business summary generation.
- `BUSINESS_CONTEXT_INTEGRATION_REPORT.md` — business context and public/private
  knowledge integration.
- `RAG_CONTEXT_INTEGRATION_REPORT.md` — chat, document RAG, and task/business
  context.
- `RETRIEVAL_PIPELINE_REPORT.md` — retrieval implementation and validation.

The reports may describe work completed at different times and therefore may
show different historical test commands or counts. The verification below
records the results available for the latest communication-related regression
run, rather than combining historical counts.

## 5. Verification results

### Automated regression tests

Executed:

```powershell
python -m unittest AI_service.test_communication AI_service.test_business_summary AI_service.test_chat_api AI_service.test_customer_insights AI_service.test_rag_api -v
```

**Result: 76 tests passed.** Communication and other model-dependent tests use
mocked model responses where appropriate. This suite is automated regression
coverage, not a 76-request live Gemini test.

### Live Gemini smoke test

Two synthetic authenticated requests were sent through the communication API
to the configured `gemini-3.5-flash-lite` model:

- A short empathetic English follow-up email with recipient context and key
  points.
- A short polite Spanish reminder message.

Both returned HTTP 200 with structured output. Business retrieval was stubbed
empty for this smoke test; no customer records or personal data were used.
This confirms a limited live integration path, not general model quality or
reliability.

### Static and formatting checks

- Pylance reported no syntax errors in the edited communication schema,
  service, and tests.
- Pylance diagnostics for the communication schema and service were empty.
- `git diff --check` completed without whitespace errors for the final
  communication report update.

The customer-insights report separately documents its own mocked test run and
local HTTP route check. Those results are not live production data analysis.

## 6. Run instructions

From the repository root in PowerShell, configure the required environment
variables and start the application:

```powershell
python -m pip install -r requirements.txt
$env:GEMINI_API_KEY = "your-key"
$env:AUTH_SECRET = "a-long-random-secret"
$env:DATABASE_PATH = "data/assistant.db"
uvicorn AI_service.api:app --reload
```

Run the tested API regression suites:

```powershell
python -m unittest AI_service.test_communication AI_service.test_business_summary AI_service.test_chat_api AI_service.test_customer_insights AI_service.test_rag_api -v
```

## 7. Known limitations

- There are no normalized business, task, customer, support-ticket, feedback,
  or transaction tables. Business/task request context is not independently
  verified, and customer insights rely on text in user-uploaded documents.
- Customer insights use conservative keyword matching. Counts are text
  mentions and documents, not verified unique-customer statistics or ledger
  totals.
- Upload timestamps cannot reliably establish when a described customer event
  occurred.
- Prepared public business knowledge and its vector cache are in memory;
  admin-added knowledge may not persist across restarts.
- Prompt constraints and schema validation reduce unsupported generation but
  cannot guarantee that a language model never hallucinates. Review generated
  business communications before use.
- Live model verification covered only two synthetic communication requests.
- No browser screenshot was captured as part of the API verification.
