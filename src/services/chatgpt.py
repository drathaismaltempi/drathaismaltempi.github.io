"""Service helpers for communicating with OpenAI's ChatGPT APIs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from openai import OpenAI

from src.config import settings


@dataclass
class TriagePrompt:
    """Bundle the information required to create a triage prompt."""

    patient: Dict[str, Any]
    complaints: Dict[str, Any]
    exams: Dict[str, Any]
    exam_analysis: Optional[Dict[str, Any]] = None

    def render(self) -> str:
        """Convert the triage information into a natural language prompt."""

        patient_block = json.dumps(self.patient, indent=2, sort_keys=True)
        complaints_block = json.dumps(self.complaints, indent=2, sort_keys=True)
        exam_block = json.dumps(self.exams, indent=2, sort_keys=True)
        analysis_block = (
            json.dumps(self.exam_analysis, indent=2, sort_keys=True)
            if self.exam_analysis
            else "None provided"
        )
        return (
            "You are a medical triage assistant. Review the following patient information\n"
            "and provide a prioritized list of concerns, recommended next steps, and\n"
            "any critical warnings that should be escalated immediately.\n\n"
            f"Patient demographics:\n{patient_block}\n\n"
            f"Patient complaints:\n{complaints_block}\n\n"
            f"Exam files metadata:\n{exam_block}\n\n"
            f"OCR exam analysis summary:\n{analysis_block}\n\n"
            "Respond using JSON with the keys 'priority_level', 'summary',\n"
            "'recommended_actions', and 'follow_up'."
        )


@dataclass
class PhysicianSummaryPrompt:
    """Prompt bundle for generating the physician-facing summary."""

    patient: Dict[str, Any]
    complaints: List[Dict[str, Any]]
    exams: List[Dict[str, Any]]
    exam_analysis: Optional[Dict[str, Any]]
    triage_response: Dict[str, Any]

    def render(self) -> str:
        """Return a detailed instruction set for the physician summary."""

        patient_block = json.dumps(self.patient, indent=2, sort_keys=True)
        complaints_block = json.dumps(self.complaints, indent=2, sort_keys=True)
        exams_block = json.dumps(self.exams, indent=2, sort_keys=True)
        analysis_block = (
            json.dumps(self.exam_analysis, indent=2, sort_keys=True)
            if self.exam_analysis
            else "None"
        )
        triage_block = json.dumps(self.triage_response, indent=2, sort_keys=True)

        return (
            "Você é um assistente médico que prepara e-mails estruturados para o(a) médico(a).\n"
            "Leia atentamente os dados do paciente, queixas, exames extraídos por OCR e o resumo\n"
            "de triagem já gerado.\n\n"
            "Monte uma saída **em JSON** seguindo exatamente o formato a seguir:\n"
            "{\n"
            "  \"orchestration_payload\": { ... objeto seguindo o esquema fornecido ... },\n"
            "  \"email\": {\"to\": \"...\", \"subject\": \"...\", \"body_markdown\": \"...\"}\n"
            "}\n\n"
            "O campo `orchestration_payload` deve corresponder fielmente ao JSON descrito abaixo,"
            " preenchendo todos os campos com informações observadas ou inferidas de forma prudente.\n"
            "Siga o template:\n"
            "{\n"
            "  \"paciente\": {\n"
            "    \"nome\": \"\",\n"
            "    \"data_nascimento\": \"\",\n"
            "    \"contatos\": {\"telefone\": \"\", \"email\": \"\"}\n"
            "  },\n"
            "  \"queixa_principal\": \"\",\n"
            "  \"contexto\": {\n"
            "    \"doencas_previas\": [],\n"
            "    \"medicamentos_suplementos\": [],\n"
            "    \"alergias\": [],\n"
            "    \"habitos\": {\"sono\": \"\", \"atividade_fisica\": \"\", \"tabaco_alcool\": \"\"}\n"
            "  },\n"
            "  \"exames\": [ ... ],\n"
            "  \"sumario\": {\n"
            "    \"dentro_referencia\": [],\n"
            "    \"fora_referencia\": [],\n"
            "    \"limitacoes\": []\n"
            "  },\n"
            "  \"correlacao_sintomas_exames\": [],\n"
            "  \"hipoteses_diferenciais\": [],\n"
            "  \"sugestoes_integrativas_ayurveda\": [],\n"
            "  \"urgencia_detectada\": false,\n"
            "  \"email\": {\n"
            "    \"to\": \"drathaismaltempi@outlook.com\",\n"
            "    \"assunto\": \"\",\n"
            "    \"corpo_markdown\": \"\"\n"
            "  }\n"
            "}\n\n"
            "Preencha campos vazios com strings vazias quando não houver informação.\n"
            "Liste apenas dados com suporte no material fornecido.\n"
            "Use linguagem neutra e orientada ao médico nos itens clínicos.\n"
            "As hipóteses diferenciais devem ser verbos no infinitivo iniciando com 'considerar'.\n"
            "As sugestões integrativas/Ayurveda são educativas, sem doses ou fármacos.\n"
            "`urgencia_detectada` é true somente se sintomas graves ou alertas críticos aparecerem.\n\n"
            "Para o corpo do e-mail (campo `body_markdown`), gere texto em português iniciando com"
            " 'Dr(a).,' e seguindo a estrutura solicitada (itens 1 a 9, tabela em Markdown).\n"
            "O assunto deve seguir o formato `[Triagem] Nome do Paciente — AAAA-MM-DD`, usando a data"
            " mais recente entre hoje e as datas conhecidas dos exames/sintomas.\n"
            "Sempre utilize `drathaismaltempi@outlook.com` como destinatário (`to`).\n"
            "Inclua uma seção final 'Anexos: arquivos originais enviados pelo paciente.'.\n"
            "Não adicione comentários fora do JSON requisitado.\n\n"
            "Dados do paciente:\n"
            f"{patient_block}\n\n"
            "Queixas:\n"
            f"{complaints_block}\n\n"
            "Exames fornecidos:\n"
            f"{exams_block}\n\n"
            "Resumo OCR:\n"
            f"{analysis_block}\n\n"
            "Resposta de triagem existente:\n"
            f"{triage_block}"
        )


class ChatGPTService:
    """Wrapper around the OpenAI client for the triage workflow."""

    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not configured. Set the environment variable before running the service."
            )
        self._client = OpenAI(api_key=settings.openai_api_key)

    def triage(self, prompt: TriagePrompt) -> Dict[str, Any]:
        """Send the triage prompt to ChatGPT and return the structured response."""

        completion = self._client.responses.create(
            model=settings.openai_model,
            input=[{"role": "user", "content": prompt.render()}],
            response_format={"type": "json_object"},
        )
        message = completion.output[0].content[0].text  # type: ignore[index]
        return json.loads(message)

    def physician_summary(self, prompt: PhysicianSummaryPrompt) -> Dict[str, Any]:
        """Generate the physician-oriented JSON summary and email body."""

        completion = self._client.responses.create(
            model=settings.openai_model,
            input=[{"role": "user", "content": prompt.render()}],
            response_format={"type": "json_object"},
        )
        message = completion.output[0].content[0].text  # type: ignore[index]
        return json.loads(message)


__all__ = ["ChatGPTService", "TriagePrompt", "PhysicianSummaryPrompt"]
