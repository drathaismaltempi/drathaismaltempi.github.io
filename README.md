# Clinical Triage Backend

This repository now includes a FastAPI backend that accepts clinical intake forms, forwards the
information to OpenAI's ChatGPT models, and stores request/response logs for future review.

## Project Structure

```
.
├── requirements.txt        # Python dependencies for the backend
└── src/
    ├── api.py              # FastAPI application and request models
    ├── config.py           # Environment driven configuration helpers
    ├── services/
    │   ├── chatgpt.py      # Prompt construction and ChatGPT client wrappers
    │   ├── emailer.py      # SMTP helper for dispatching physician summaries
    │   └── exams.py        # OCR and laboratory exam interpretation pipeline
    └── storage.py          # SQLite-backed request/response logging utilities
```

## Authentication

The `/triage` and `/pre-atendimento` endpoints expect an `X-API-Key` header when the
`TRIAGE_API_TOKEN` environment variable is configured. Calls without the header (or with an
incorrect token) are rejected with a `401 Unauthorized` response. Incoming values are compared after
trimming surrounding whitespace so secrets copied from dashboard UIs (which sometimes append new
lines) continue to work, but the characters still need to match exactly. When a mismatch occurs the
application logs SHA-256 fingerprints of the provided and expected values (first eight hex
characters only) to help diagnose typos without exposing the secrets themselves.

For uptime monitors, the root path (`GET /`) returns `{ "status": "ok" }` with HTTP `200`.

```
X-API-Key: ${TRIAGE_API_TOKEN}
```

## Environment Variables

- `OPENAI_API_KEY` (required): API key used to authenticate with OpenAI. Requests return `500`
  with a configuration error message when this is missing.
- `OPENAI_MODEL` (optional): ChatGPT model identifier to call (defaults to `gpt-5.1-mini`). If the
  configured model is unavailable, the backend automatically falls back to `gpt-5.1-mini` and logs a
  warning so triage requests continue to succeed.
- `TRIAGE_API_TOKEN` (optional): Shared secret for authenticating inbound requests.
- `TRIAGE_LOG_DB_PATH` (optional): Path to the SQLite database used for request/response auditing.
  Defaults to `data/triage_logs.db`.
- `TRIAGE_UPLOAD_DIR` (optional): Directory where uploaded exam files from the public form are
  stored. Defaults to `data/uploads`.
- `SMTP_HOST`, `SMTP_PORT` (optional): SMTP server coordinates for sending physician summaries.
- `SMTP_USERNAME`, `SMTP_PASSWORD` (required for email): Credentials for the Gmail/App Password
  used to deliver the structured summaries.
- `SMTP_SENDER` (optional): Address to appear in the `From` header. Defaults to
  `drathaispreconsulta@gmail.com`.
- `PHYSICIAN_EMAIL_TO` (optional): Destination inbox for the summaries. Defaults to
  `drathaismaltempi@outlook.com`.

Environment variables can be stored in a `.env` file located in the project root during local
development. The configuration module loads and expands file system paths automatically.

### Configuring the OpenAI API key and model

1. Create a `.env` file in the project root (next to `README.md`) if it does not exist.
2. Add the following lines, replacing the placeholders with your OpenAI credentials and preferred
   model:

   ```env
   OPENAI_API_KEY=sk-your-secret-key
   OPENAI_MODEL=gpt-5.1-mini
   ```

3. Restart the application (or reload your process manager) so the new environment variables are
   picked up.

> **Do not hard-code secrets in `src/config.py`.** The `Settings` class automatically reads the
> values from the environment (or `.env` file) at runtime, so you should never replace
> `OPENAI_API_KEY` in the source code with your real key. Keeping the key outside the repository
> prevents accidental leaks when committing or sharing the project.

When hosted on a platform that manages secrets (Docker, Render, Vercel, AWS, etc.), set the same
variables in the provider's configuration UI instead of the `.env` file. Any model string supported
by the [Responses API](https://platform.openai.com/docs/guides/responses) can be supplied via
`OPENAI_MODEL` without code changes.

## Payload Schema

### Request (`POST /triage`)

```jsonc
{
  "patient": {
    "patient_id": "optional string",
    "name": "optional string",
    "age": 30,
    "sex": "optional string",
    "contact_information": {
      "phone": "+1-555-123-4567",
      "email": "patient@example.com"
    }
  },
  "complaints": [
    {
      "summary": "Chief complaint text",
      "onset": "3 days ago",
      "severity": "moderate",
      "associated_symptoms": ["nausea", "dizziness"]
    }
  ],
  "exam_files": [
    {
      "label": "Chest X-Ray",
      "url": "https://example.com/secure/xray-123",
      "file_type": "image/jpeg",
      "description": "AP chest radiograph"
    }
  ]
}
```

### Response

```jsonc
{
  "priority_level": "high",
  "summary": "Short triage assessment",
  "recommended_actions": [
    "Action item 1",
    "Action item 2"
  ],
  "follow_up": "Optional follow-up note"
}
```

## Laboratory exam OCR and classification

- Uploaded PDF or image-based exam files (`file://` URIs produced by the public form) are parsed by
  `src/services/exams.py` using `pdfminer.six` for text-based PDFs and `pytesseract` (Tesseract OCR) for
  raster images.
- Extracted measurements are normalized, matched against built-in reference ranges, and classified as
  `within_range`, `out_of_range`, or `critical`. Critical findings and a condensed summary are added to
  the triage prompt so the AI model can react to abnormal values.
- When OCR fails, the captured error is attached to the exam metadata so operators can troubleshoot
  the ingestion issue without blocking the rest of the triage workflow.

> **Note:** Image OCR requires the native [Tesseract](https://github.com/tesseract-ocr/tesseract)
> binary to be installed on the host in addition to the Python `pytesseract` package. PDF text
> extraction does not require extra system dependencies.

## Structured physician e-mail summaries

- After the triage JSON is produced, the backend now prompts ChatGPT a second time to build a
  physician-facing orchestration payload and Markdown e-mail that follows the requested template
  (dados do paciente, tabela de exames, hipóteses diferenciais, sugestões integrativas, alertas,
  etc.).
- The orchestration JSON is attached to the API response under `physician_summary` and stored in the
  audit log so downstream systems can ingest the structured view.
- The generated Markdown body is delivered via SMTP (Gmail) to
  `drathaismaltempi@outlook.com`. Configure `SMTP_USERNAME`/`SMTP_PASSWORD` with the
  `drathaispreconsulta@gmail.com` account or another credentialed sender. Failures are surfaced in
  the API response (`physician_summary.email.sent`/`error`). When the submission contains
  `file://` exam uploads, the original documents are attached to the outgoing e-mail so the
  physician can open them directly from the inbox.

## Running Locally

1. Create and activate a virtual environment.
2. Install dependencies with `pip install -r requirements.txt`. Install the Tesseract binary if you
   plan to process image-based exams.
3. Export the required environment variables (or create a `.env` file).
4. Start the application using Uvicorn:

   ```bash
   uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload
   ```

The API documentation is available at `http://localhost:8000/docs`.

## Public form submissions (`POST /pre-atendimento`)

The Google Sites embed shared in the project README can POST multipart form-data directly to the
`/pre-atendimento` endpoint. The backend automatically maps the Portuguese field names to the
internal triage schema, persists any uploaded exam files into `TRIAGE_UPLOAD_DIR`, and forwards the
structured payload to ChatGPT just like the JSON endpoint.

Important details:

- **Honeypot and consent:** Submissions that fill the hidden `_honey` field or omit the
  `consentimento` checkbox are rejected with `400 Bad Request`.
- **Exam uploads:** `examesSangue` and `examesImagem` files are written to disk. The stored `file://`
  URI is passed to the AI model and recorded in the audit logs for traceability.
- **Generated patient IDs:** When the public form omits a `patient_id`, one is generated using the
  contact details plus a random suffix to maintain traceability in the audit logs.

### Checklist to make the public form work end-to-end

1. **Publish the FastAPI service** somewhere accessible over HTTPS (Render, Fly.io, a VPS, etc.).
   On Render, open your web service and copy the **Public URL** shown near the top of the dashboard
   (for example `https://seu-backend.onrender.com`). Append `/pre-atendimento` to that URL so the
   full endpoint becomes `https://seu-backend.onrender.com/pre-atendimento`.
2. **Replace the placeholder endpoint** in `Pr-atendimento.html` (or the Google Sites embed) with
   the real URL so the browser submits the form to your server.
3. **Allow the site origin through CORS** by setting `TRIAGE_CORS_ORIGINS` to the domain that hosts
   the form (e.g. `TRIAGE_CORS_ORIGINS=https://www.drathaismaltempi.com.br`). This enables the
   browser to complete the preflight `OPTIONS` request before uploading the data.
4. **Provide the required secrets on the server:** `OPENAI_API_KEY` for the AI analysis and the
   `SMTP_*` variables (plus `PHYSICIAN_EMAIL_TO` if you want to override the default) so the e-mail
   can be delivered. Add an app password if your provider is Gmail.
5. **Decide how to protect the endpoint.** If you set `TRIAGE_API_TOKEN`, the deployment platform
   must inject the token into the `X-API-Key` header (for example, via a reverse proxy or edge
   worker). Otherwise leave it unset for the public form.

Once those pieces are in place, submitting the site form will call the FastAPI endpoint, run the AI
analysis, and dispatch the physician summary e-mail automatically.

## Deployment

- **Containerization:** Build a Docker image using a Python base, install the requirements, copy the
  `src/` directory, and run `uvicorn src.api:app` as the container's entrypoint.
- **Serverless:** Package the `src/` directory with the dependencies in a deployment bundle supported
  by your provider (e.g., AWS Lambda with API Gateway via Mangum or Azure Functions with ASGI support).
- **Security:** Ensure secrets (`OPENAI_API_KEY`, `TRIAGE_API_TOKEN`) are injected via the provider's
  secret management system. Configure secure storage (managed databases or encrypted volumes) for the
  SQLite log file when running outside of local development.
- **Render Start Command:** Configure the Render service to launch Uvicorn with the platform-provided
  port: `uvicorn src.api:app --host 0.0.0.0 --port $PORT`. Render sets the `$PORT` environment
  variable for each deployment and scaling event, so referencing it ensures the web service binds to
  the correct socket.
- **Render Python Runtime:** Add a `runtime.txt` file containing `python-3.12.3` (or another supported
  3.12 release). This keeps the deployed interpreter aligned with local development. The PDF pipeline
  now uses `pdfminer.six`, which ships universal wheels compatible with Python 3.13+, so upgrading the
  runtime is safe once your infrastructure is ready.

## Auditing

Every triage request and its corresponding response are written to the SQLite database configured by
`TRIAGE_LOG_DB_PATH`. The records include timestamps, the submitted payload, and the generated
recommendations, enabling retrospective review and compliance reporting.
