"""Service helpers for communicating with OpenAI's ChatGPT APIs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict

from openai import OpenAI

from src.config import settings


@dataclass
class TriagePrompt:
    """Bundle the information required to create a triage prompt."""

    patient: Dict[str, Any]
    complaints: Dict[str, Any]
    exams: Dict[str, Any]

    def render(self) -> str:
        """Convert the triage information into a natural language prompt."""

        patient_block = json.dumps(self.patient, indent=2, sort_keys=True)
        complaints_block = json.dumps(self.complaints, indent=2, sort_keys=True)
        exam_block = json.dumps(self.exams, indent=2, sort_keys=True)
        return (
            "You are a medical triage assistant. Review the following patient information\n"
            "and provide a prioritized list of concerns, recommended next steps, and\n"
            "any critical warnings that should be escalated immediately.\n\n"
            f"Patient demographics:\n{patient_block}\n\n"
            f"Patient complaints:\n{complaints_block}\n\n"
            f"Exam files metadata:\n{exam_block}\n\n"
            "Respond using JSON with the keys 'priority_level', 'summary',\n"
            "'recommended_actions', and 'follow_up'."
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
            model="gpt-4.1-mini",
            input=[{"role": "user", "content": prompt.render()}],
            response_format={"type": "json_object"},
        )
        message = completion.output[0].content[0].text  # type: ignore[index]
        return json.loads(message)


__all__ = ["ChatGPTService", "TriagePrompt"]
