"""FastAPI application exposing the triage endpoint."""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field

from src.config import settings
from src.services.chatgpt import ChatGPTService, TriagePrompt
from src.storage import LogRecord, persist_log

app = FastAPI(title="Clinical Triage API", version="0.1.0")


class PatientDemographics(BaseModel):
    """Structured patient demographic information."""

    patient_id: Optional[str] = Field(
        default=None, description="Unique identifier for the patient provided by the client."
    )
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
    url: Optional[str] = Field(
        default=None, description="Secure URL or file URI where the exam file can be accessed."
    )
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


def _generate_patient_id(patient: Dict[str, Any]) -> str:
    """Generate a deterministic-ish patient id using available info."""

    contact = (patient.get("contact_information") or {}).get("primary")
    name = patient.get("name")
    base = contact or name or "patient"
    slug = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")
    if not slug:
        slug = "patient"
    return f"{slug}-{uuid4().hex[:8]}"


def _store_uploads(label: str, uploads: List[UploadFile]) -> List[ExamFile]:
    """Persist uploaded exam files and return their metadata."""

    saved: List[ExamFile] = []
    if not uploads:
        return saved

    upload_dir: Path = settings.uploads_dir
    upload_dir.mkdir(parents=True, exist_ok=True)

    for upload in uploads:
        if not upload or not upload.filename:
            continue
        suffix = Path(upload.filename).suffix
        filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid4().hex}{suffix}"
        destination = upload_dir / filename
        with destination.open("wb") as buffer:
            upload.file.seek(0)
            shutil.copyfileobj(upload.file, buffer)
        upload.file.close()
        saved.append(
            ExamFile(
                label=f"{label}: {upload.filename}",
                url=destination.resolve().as_uri(),
                file_type=upload.content_type,
                description="Uploaded via pre-atendimento form.",
            )
        )
    return saved


def _perform_triage(request: TriageRequest) -> TriageResponse:
    """Shared triage execution used by both JSON and form submissions."""

    payload = request.dict()
    patient = payload.setdefault("patient", {})
    if not patient.get("patient_id"):
        patient["patient_id"] = _generate_patient_id(patient)

    try:
        service = ChatGPTService()
        prompt = TriagePrompt(
            patient=patient,
            complaints={"items": payload.get("complaints", [])},
            exams={"items": payload.get("exam_files", [])},
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
            request_payload=payload,
            response_payload=gpt_response,
        )
    )

    return TriageResponse(**gpt_response)


@app.post("/triage", response_model=TriageResponse, dependencies=[Depends(authenticate)])
def triage(request: TriageRequest) -> TriageResponse:
    """Perform a triage assessment from a JSON payload."""

    return _perform_triage(request)


@app.post(
    "/pre-atendimento",
    response_model=TriageResponse,
    dependencies=[Depends(authenticate)],
)
async def pre_atendimento(
    nomeCompleto: str = Form(...),
    idade: Optional[int] = Form(None),
    contato: str = Form(...),
    sintomasDescricao: str = Form(...),
    sintomasInicio: Optional[str] = Form(None),
    sintomasIntensidade: Optional[int] = Form(None),
    sintomasFatores: Optional[str] = Form(None),
    historicoComorbidades: Optional[str] = Form(None),
    historicoMedicacoes: Optional[str] = Form(None),
    historicoAlergias: Optional[str] = Form(None),
    habitosSono: Optional[str] = Form(None),
    habitosEstresse: Optional[int] = Form(None),
    habitosAlimentacao: Optional[str] = Form(None),
    habitosAtividade: Optional[str] = Form(None),
    examesSangue: Optional[List[UploadFile]] = File(default=None),
    examesImagem: Optional[List[UploadFile]] = File(default=None),
    consentimento: bool = Form(...),
    _honey: Optional[str] = Form(None),
) -> TriageResponse:
    """Accept submissions from the public-facing Google Sites form."""

    if _honey:  # honeypot triggered
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Spam detected.")
    if not consentimento:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="É necessário aceitar o termo de consentimento.",
        )

    exam_files: List[ExamFile] = []
    if examesSangue:
        exam_files.extend(_store_uploads("Exame de sangue", examesSangue))
    if examesImagem:
        exam_files.extend(_store_uploads("Exame de imagem", examesImagem))

    complaint_details = Complaint(
        summary=sintomasDescricao,
        onset=sintomasInicio,
        severity=str(sintomasIntensidade) if sintomasIntensidade is not None else None,
        associated_symptoms=[sintomasFatores] if sintomasFatores else None,
    )

    patient = PatientDemographics(
        name=nomeCompleto,
        age=idade,
        contact_information={"primary": contato},
    )

    history_notes: List[str] = []
    if historicoComorbidades:
        history_notes.append(f"Comorbidades/cirurgias: {historicoComorbidades}")
    if historicoMedicacoes:
        history_notes.append(f"Medicações/suplementos: {historicoMedicacoes}")
    if historicoAlergias:
        history_notes.append(f"Alergias conhecidas: {historicoAlergias}")
    if habitosSono:
        history_notes.append(f"Sono: {habitosSono}")
    if habitosEstresse is not None:
        history_notes.append(f"Nível de estresse: {habitosEstresse}")
    if habitosAlimentacao:
        history_notes.append(f"Alimentação: {habitosAlimentacao}")
    if habitosAtividade:
        history_notes.append(f"Atividade física: {habitosAtividade}")

    if history_notes:
        if complaint_details.associated_symptoms is None:
            complaint_details.associated_symptoms = history_notes
        else:
            complaint_details.associated_symptoms.extend(history_notes)

    triage_request = TriageRequest(
        patient=patient,
        complaints=[complaint_details],
        exam_files=exam_files,
    )

    return _perform_triage(triage_request)


__all__ = ["app"]
