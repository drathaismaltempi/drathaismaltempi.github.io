"""FastAPI application exposing the triage endpoint."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from src.config import settings
from src.services.chatgpt import ChatGPTService, TriagePrompt
from src.storage import LogRecord, persist_log

app = FastAPI(title="Clinical Triage API", version="0.1.0")


class PatientDemographics(BaseModel):
    """Structured patient demographic information."""

    patient_id: str = Field(..., description="Unique identifier for the patient.")
    name: Optional[str] = Field(None, description="Full name of the patient.")
    age: Optional[int] = Field(None, description="Age in years.")
    sex: Optional[str] = Field(None, description="Sex or gender identity.")
    contact_information: Optional[Dict[str, Any]] = Field(
        default=None, description="Preferred methods to reach the patient."
    )


class Complaint(BaseModel):
    """A primary complaint provided by the patient."""

    summary: str = Field(..., description="Short description of the complaint.")
    onset: Optional[str] = Field(None, description="Reported onset time frame.")
    severity: Optional[str] = Field(None, description="Patient-reported severity.")
    associated_symptoms: Optional[List[str]] = Field(
        default=None, description="List of additional symptoms mentioned in the complaint."
    )


class ExamFile(BaseModel):
    """Metadata describing external exam files available for review."""

    label: str = Field(..., description="Human readable label for the exam file.")
    url: str = Field(..., description="Secure URL where the exam file can be accessed.")
    file_type: Optional[str] = Field(None, description="Media type of the file, e.g., image/jpeg.")
    description: Optional[str] = Field(None, description="Free text explaining the file contents.")


class TriageRequest(BaseModel):
    """Payload accepted by the triage endpoint."""

    patient: PatientDemographics
    complaints: List[Complaint] = Field(..., description="List of patient complaints.")
    exam_files: List[ExamFile] = Field(default_factory=list, description="Related exam files.")


class TriageResponse(BaseModel):
    """Structured response returned by the triage endpoint."""

    priority_level: str
    summary: str
    recommended_actions: List[str]
    follow_up: Optional[str] = None


def authenticate(x_api_key: Optional[str] = Header(None)) -> None:
    """Verify that the caller provided the expected API key."""

    if settings.api_auth_token and x_api_key != settings.api_auth_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key provided in X-API-Key header.",
        )


@app.post("/triage", response_model=TriageResponse, dependencies=[Depends(authenticate)])
def triage(request: TriageRequest) -> TriageResponse:
    """Perform a triage assessment by delegating to ChatGPT."""

    try:
        service = ChatGPTService()
        prompt = TriagePrompt(
            patient=request.patient.dict(),
            complaints={"items": [complaint.dict() for complaint in request.complaints]},
            exams={"items": [exam.dict() for exam in request.exam_files]},
        )
        gpt_response = service.triage(prompt)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive logging
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unable to complete triage: {exc}",
        ) from exc

    persist_log(
        LogRecord(
            created_at=datetime.utcnow(),
            request_payload=request.dict(),
            response_payload=gpt_response,
        )
    )

    return TriageResponse(**gpt_response)


__all__ = ["app"]
