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
    │   └── chatgpt.py      # Prompt construction and ChatGPT client wrapper
    └── storage.py          # SQLite-backed request/response logging utilities
```

## Authentication

The `/triage` endpoint expects an `X-API-Key` header when the `TRIAGE_API_TOKEN` environment
variable is configured. Calls without the header (or with an incorrect token) are rejected with a
`401 Unauthorized` response.

```
X-API-Key: ${TRIAGE_API_TOKEN}
```

## Environment Variables

- `OPENAI_API_KEY` (required): API key used to authenticate with OpenAI.
- `TRIAGE_API_TOKEN` (optional): Shared secret for authenticating inbound requests.
- `TRIAGE_LOG_DB_PATH` (optional): Path to the SQLite database used for request/response auditing.
  Defaults to `data/triage_logs.db`.

Environment variables can be stored in a `.env` file located in the project root during local
development. The configuration module loads and expands file system paths automatically.

## Payload Schema

### Request (`POST /triage`)

```jsonc
{
  "patient": {
    "patient_id": "string",
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

## Running Locally

1. Create and activate a virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Export the required environment variables (or create a `.env` file).
4. Start the application using Uvicorn:

   ```bash
   uvicorn src.api:app --host 0.0.0.0 --port 8000 --reload
   ```

The API documentation is available at `http://localhost:8000/docs`.

## Deployment

- **Containerization:** Build a Docker image using a Python base, install the requirements, copy the
  `src/` directory, and run `uvicorn src.api:app` as the container's entrypoint.
- **Serverless:** Package the `src/` directory with the dependencies in a deployment bundle supported
  by your provider (e.g., AWS Lambda with API Gateway via Mangum or Azure Functions with ASGI support).
- **Security:** Ensure secrets (`OPENAI_API_KEY`, `TRIAGE_API_TOKEN`) are injected via the provider's
  secret management system. Configure secure storage (managed databases or encrypted volumes) for the
  SQLite log file when running outside of local development.

## Auditing

Every triage request and its corresponding response are written to the SQLite database configured by
`TRIAGE_LOG_DB_PATH`. The records include timestamps, the submitted payload, and the generated
recommendations, enabling retrospective review and compliance reporting.
