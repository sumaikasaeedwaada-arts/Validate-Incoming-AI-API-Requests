# AI Chat and Knowledge Base Integration Report

## Architecture

The active application is `AI_service.api:app`, built with FastAPI and
Pydantic. The authenticated chat path is:

```text
Browser / POST /chat
  -> AI_service.routes.chat
  -> AI_service.controllers.chat_controller
  -> AI_service.services.chat_service
  -> authentication and conversation ownership checks
  -> SQLite conversation history and user-owned document retrieval
  -> Gemini query embeddings / cosine ranking / grounded prompt
  -> configured Gemini chat model
  -> persisted answer and source citations
```

`AI_service.rag` is the shared document retrieval implementation; the project
does not use a separate knowledge-base service or a second vector database.
The browser UI uses `/api/conversations/{id}/messages`, while `/chat` remains
available as a compatible authenticated endpoint.

## Files changed for this integration

- `AI_service/services/chat_service.py` now carries prior user questions into
  the document retrieval query when resolving follow-ups. Earlier assistant
  responses are not added to that query as retrieval evidence.
- `AI_service/static/app.js` fixes a browser-global shadowing bug that
  prevented the uploaded document list from refreshing after upload.
- `AI_service/test_rag_api.py` adds an API-level follow-up test proving the
  prior question and current follow-up are used together, a matching source is
  cited, and the assistant's previous answer is not used as retrieval evidence.
- `AI_CHAT_KNOWLEDGE_BASE_REPORT.md` documents the current architecture and
  verification.
- `AI_CHAT_KB_SMOKE_TEST.png` captures the successful local chat response and
  its uploaded-document citation.

The worktree contained unrelated pre-existing modifications; those were left
untouched.

## Document ingestion, embeddings, and vector storage

Authenticated `POST /api/documents` accepts PDF, DOCX, and UTF-8 TXT files up
to 8 MB. The existing pipeline extracts text, splits it into overlapping
chunks, generates embeddings through the configured Gemini embedding model,
then atomically stores text, page metadata, and vectors in SQLite. Stable
`(document_id, chunk_index)` uniqueness and upserts prevent duplicate chunk
records for the same document. Deleting an owned document deletes its chunks
through the foreign-key cascade.

The vector index configuration is persisted in `vector_index_state`, including
embedding model, established vector dimension, and cosine similarity metric.
Search validates the query vector and index dimensions, filters rows by the
authenticated user's ID before ranking, applies the configured minimum
relevance threshold, and returns the highest scoring chunks with document
metadata. Search does not embed a query when that user has no indexed chunks.
The current implementation performs an exact SQLite/NumPy scan; it is
appropriate for a single-node/modest corpus and is not a distributed vector
database.

## Chat and retrieval workflow

`POST /chat` accepts a validated `ChatRequest` extending `MessageRequest`:

```json
{
  "message": "What are the company's main services?",
  "conversation_id": "optional-existing-conversation-id"
}
```

The `conversation_id` may be omitted to create a conversation. An owned
conversation's recent history is loaded before retrieval. For follow-up
questions, the two most recent user questions are included with the current
question in the retrieval query; prior assistant answers remain in the chat
prompt history but do not influence which document passages are considered
retrieval evidence. Retrieved excerpts, relevant prepared public business
knowledge, optional request business/task context, and bounded conversation
history are assembled for the configured model.

The system and chat prompts instruct the model to treat retrieved text as
untrusted data rather than instructions, prioritize relevant retrieved facts,
distinguish missing or conflicting information, avoid invented facts and
citations, and cite document evidence using its assigned `[n]` reference.
Only retrieved chunks are cited. Empty retrieval produces no document
citations; the model is instructed to state when information is unavailable.
Generated answers and their citations are stored as conversation messages.

Successful responses retain the existing contract:

```json
{
  "conversation_id": "conversation-id",
  "response": "The company provides bookkeeping and payroll services [1].",
  "citations": [
    {
      "index": 1,
      "document_id": "document-id",
      "filename": "business-profile.txt",
      "page_number": null,
      "score": 0.91
    }
  ],
  "created_at": "UTC timestamp"
}
```

An empty or whitespace-only message fails Pydantic validation with HTTP 422.
Chat/model and document retrieval failures are returned as sanitized service
errors (HTTP 503); authentication failures return HTTP 401; attempts to use a
conversation or document not owned by the caller return HTTP 404. FastAPI
validation and HTTP errors use the framework's structured JSON `detail`
response.

## Security and data isolation

- All chat, conversation, upload, document, and index-status operations
  require a valid bearer token.
- Conversation reads and writes are checked against the authenticated user.
- Document retrieval SQL scopes rows to `documents.user_id`; document list and
  delete routes also apply the user ID filter.
- Conversation history and persisted citations are scoped to the owned
  conversation.
- API keys and provider exception details are not returned in error responses.
- SQLite persistence is configured with `DATABASE_PATH`; Gemini chat and
  embedding model names/timeouts are configured through the existing
  `GEMINI_MODEL`, `GEMINI_EMBEDDING_MODEL`, and `GEMINI_TIMEOUT_MS` settings.

The data model currently treats each account as its own business/tenant.
There is no separate business-membership or shared-company authorization
model in this repository; multi-user shared business workspaces would require
an explicit business/tenant membership model before broadening access.

## Tests and verification

Executed:

```powershell
& '.venv\Scripts\python.exe' -m unittest `
  AI_service.test_communication `
  AI_service.test_business_summary `
  AI_service.test_chat_api `
  AI_service.test_customer_insights `
  AI_service.test_rag_api `
  test_chat_api `
  test_rag_api
```

**Result: 113 tests passed.** The relevant automated coverage includes
synthetic document upload and retrieval, source citation persistence,
follow-up retrieval context, empty/irrelevant knowledge, embedding/vector
failures, model timeouts, unauthorized access, user isolation, and the
existing `/chat` contract. These tests use mocked model and embedding calls
where provider behavior is involved; they are not live Gemini integration
tests.

A local browser/API smoke test also uploaded a synthetic TXT business profile
and asked, "What are the company's main services?" The API returned the
profile's bookkeeping, payroll, and tax preparation content with the source
`smoke-business-profile.txt`. The synthetic document embedding and chat
generation were mocked; SQLite chunk storage, query execution, ranking, API
authorization, and source citation ran through the real application. The
prepared public knowledge search also made live Gemini embedding requests
using the configured environment key. This was a partial live embedding
smoke test, not a live Gemini chat-generation test. The screenshot is in
[AI_CHAT_KB_SMOKE_TEST.png](./AI_CHAT_KB_SMOKE_TEST.png).

No pre-existing uploaded business-document database was available in the
workspace. The integration was verified using the synthetic profile rather
than a real customer upload; this does not establish answer quality for a
real business corpus.

## Limitations and future improvements

- SQLite vector search is an exact scan and may not scale for large corpora or
  multi-node deployments.
- One account currently equals one business access boundary; shared workspace
  membership and business-level role permissions are not implemented.
- Embedding model changes require re-embedding existing chunks; the current
  index correctly rejects model/dimension mismatches rather than silently
  mixing vectors.
- Retrieval quality is dependent on Gemini embedding similarity and the
  configured relevance threshold. An offline evaluation corpus and live
  provider integration tests should be added before production tuning.
- Larger knowledge bases may benefit from a managed vector index while
  retaining the same authenticated metadata filters and document ownership
  checks.
