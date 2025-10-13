"""OCR and laboratory exam classification utilities."""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pdfminer.high_level import extract_text as pdf_extract_text
from pdfminer.pdfparser import PDFSyntaxError
from PIL import Image
import pytesseract

LOGGER = logging.getLogger(__name__)


@dataclass
class ReferenceRange:
    """Static reference range configuration for a laboratory exam."""

    low: float
    high: float
    unit: str
    critical_low: Optional[float] = None
    critical_high: Optional[float] = None


@dataclass
class ExamMeasurement:
    """Structured representation of a parsed laboratory value."""

    name: str
    value: Optional[float]
    unit: Optional[str]
    raw_value: str
    reference_range: Optional[Tuple[float, float]] = None
    reference_unit: Optional[str] = None
    classification: str = "unknown"
    is_critical: bool = False
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the measurement for JSON consumption."""

        data: Dict[str, Any] = {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "raw_value": self.raw_value,
            "classification": self.classification,
            "is_critical": self.is_critical,
        }
        if self.reference_range:
            data["reference_range"] = {
                "low": self.reference_range[0],
                "high": self.reference_range[1],
                "unit": self.reference_unit,
            }
        if self.notes:
            data["notes"] = self.notes
        return data


@dataclass
class ExamAnalysis:
    """Output of the OCR and classification pipeline for an exam file."""

    source: str
    text_excerpt: str
    measurements: List[ExamMeasurement]
    critical_findings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the analysis for JSON consumption."""

        return {
            "source": self.source,
            "text_excerpt": self.text_excerpt,
            "measurements": [measurement.to_dict() for measurement in self.measurements],
            "critical_findings": self.critical_findings,
        }


SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".gif"}


def _normalize_unit(unit: Optional[str]) -> Optional[str]:
    if not unit:
        return None
    normalized = unit.strip().replace("µ", "u").lower()
    mapping = {
        "g/dl": "g/dL",
        "mg/dl": "mg/dL",
        "mmol/l": "mmol/L",
        "umol/l": "umol/L",
        "u/l": "U/L",
        "x10^3/ul": "10^3/uL",
        "x10^3/mm3": "10^3/uL",
        "x10^6/ul": "10^6/uL",
    }
    return mapping.get(normalized, unit.strip())


def _normalize_key(name: str) -> str:
    simplified = unicodedata.normalize("NFKD", name)
    simplified = "".join(ch for ch in simplified if not unicodedata.combining(ch))
    simplified = re.sub(r"[^a-z0-9]+", " ", simplified.lower())
    return re.sub(r"\s+", " ", simplified).strip()


def _parse_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    cleaned = value.replace(" ", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


REFERENCE_RANGES: Dict[str, ReferenceRange] = {
    _normalize_key("Hemoglobin"): ReferenceRange(low=12.0, high=17.5, unit="g/dL", critical_low=7.0, critical_high=20.0),
    _normalize_key("Hemoglobina"): ReferenceRange(low=12.0, high=17.5, unit="g/dL", critical_low=7.0, critical_high=20.0),
    _normalize_key("Hematocrit"): ReferenceRange(low=36.0, high=52.0, unit="%", critical_low=20.0, critical_high=60.0),
    _normalize_key("Leukocytes"): ReferenceRange(low=4.0, high=11.0, unit="10^3/uL", critical_low=2.0, critical_high=30.0),
    _normalize_key("Leucócitos"): ReferenceRange(low=4.0, high=11.0, unit="10^3/uL", critical_low=2.0, critical_high=30.0),
    _normalize_key("Platelets"): ReferenceRange(low=150.0, high=450.0, unit="10^3/uL", critical_low=50.0, critical_high=1000.0),
    _normalize_key("Plaquetas"): ReferenceRange(low=150.0, high=450.0, unit="10^3/uL", critical_low=50.0, critical_high=1000.0),
    _normalize_key("Creatinine"): ReferenceRange(low=0.6, high=1.3, unit="mg/dL", critical_high=10.0),
    _normalize_key("Creatinina"): ReferenceRange(low=0.6, high=1.3, unit="mg/dL", critical_high=10.0),
    _normalize_key("Glucose"): ReferenceRange(low=70.0, high=99.0, unit="mg/dL", critical_low=40.0, critical_high=500.0),
    _normalize_key("Glicose"): ReferenceRange(low=70.0, high=99.0, unit="mg/dL", critical_low=40.0, critical_high=500.0),
}


RESULT_PATTERN = re.compile(
    r"""
    ^\s*
    (?P<name>[A-Za-zÀ-ÿ0-9\-\/\s\(\)]+?)
    (?:[:\t]|\s{2,}|\s+-\s+)
    (?P<value>-?\d+(?:[\.,]\d+)?)
    \s*
    (?P<unit>[A-Za-zµ/%\^0-9]+)?
    (?:
        \s*
        (?:\(|\[)?
        (?P<ref_low>-?\d+(?:[\.,]\d+)?)
        \s*(?:-|–|to)\s*
        (?P<ref_high>-?\d+(?:[\.,]\d+)?)
        \s*(?P<ref_unit>[A-Za-zµ/%\^0-9]+)?
        (?:\)|\])?
    )?
    \s*$
    """,
    re.UNICODE | re.VERBOSE,
)


class ExamOCRPipeline:
    """End-to-end OCR and classification pipeline for laboratory exams."""

    def __init__(self, *, excerpt_length: int = 1200) -> None:
        self._excerpt_length = excerpt_length

    def analyze(self, file_path: Path) -> ExamAnalysis:
        """Extract, parse, and classify laboratory values from an exam file."""

        if not file_path.exists():
            raise FileNotFoundError(f"Exam file does not exist: {file_path}")

        text = self._extract_text(file_path)
        if not text.strip():
            raise ValueError("OCR extraction produced no text output.")

        measurements = self._parse_measurements(text)
        self._classify_measurements(measurements)
        critical_findings = [m.name for m in measurements if m.is_critical]
        excerpt = text.strip().replace("\r", " ").replace("\n\n", "\n")
        excerpt = excerpt[: self._excerpt_length]
        return ExamAnalysis(
            source=str(file_path),
            text_excerpt=excerpt,
            measurements=measurements,
            critical_findings=critical_findings,
        )

    def _extract_text(self, file_path: Path) -> str:
        suffix = file_path.suffix.lower()
        if suffix == ".pdf":
            return self._extract_pdf_text(file_path)
        if suffix in SUPPORTED_IMAGE_SUFFIXES:
            return self._extract_image_text(file_path)
        raise ValueError(f"Unsupported exam file type: {suffix}")

    @staticmethod
    def _extract_pdf_text(file_path: Path) -> str:
        try:
            text = pdf_extract_text(str(file_path))
            return text or ""
        except (PDFSyntaxError, ValueError) as exc:
            LOGGER.exception("Failed to extract text from PDF %s", file_path)
            raise ValueError(f"Unable to process PDF: {exc}") from exc
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.exception("Failed to extract text from PDF %s", file_path)
            raise ValueError(f"Unable to process PDF: {exc}") from exc

    @staticmethod
    def _extract_image_text(file_path: Path) -> str:
        try:
            with Image.open(file_path) as image:
                return pytesseract.image_to_string(image)
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.exception("Failed to extract text from image %s", file_path)
            raise ValueError(f"Unable to process image: {exc}") from exc

    def _parse_measurements(self, text: str) -> List[ExamMeasurement]:
        measurements: List[ExamMeasurement] = []
        seen: set[str] = set()

        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            match = RESULT_PATTERN.match(stripped)
            if not match:
                continue

            name = match.group("name").strip().rstrip(":")
            raw_value = match.group("value")
            value = _parse_float(raw_value)
            unit = _normalize_unit(match.group("unit"))

            ref_low = _parse_float(match.group("ref_low"))
            ref_high = _parse_float(match.group("ref_high"))
            ref_unit = _normalize_unit(match.group("ref_unit")) if match.group("ref_unit") else unit

            key = (_normalize_key(name), raw_value, unit or "")
            if key in seen:
                continue
            seen.add(key)

            measurement = ExamMeasurement(
                name=name,
                value=value,
                unit=unit,
                raw_value=raw_value,
            )
            if ref_low is not None and ref_high is not None and ref_low <= ref_high:
                measurement.reference_range = (ref_low, ref_high)
                measurement.reference_unit = ref_unit

            measurements.append(measurement)

        return measurements

    def _classify_measurements(self, measurements: List[ExamMeasurement]) -> None:
        for measurement in measurements:
            if measurement.value is None:
                measurement.classification = "unknown"
                measurement.notes.append("Value could not be parsed as a number.")
                continue

            reference = self._resolve_reference_range(measurement)

            range_to_use: Optional[Tuple[float, float]] = measurement.reference_range
            range_unit = measurement.reference_unit
            if range_to_use is None and reference:
                range_to_use = (reference.low, reference.high)
                range_unit = reference.unit
                measurement.reference_range = range_to_use
                measurement.reference_unit = reference.unit

            if range_to_use:
                low, high = range_to_use
                if measurement.unit and range_unit and measurement.unit != range_unit:
                    measurement.notes.append(
                        f"Unit mismatch between measured value ({measurement.unit}) and reference ({range_unit})."
                    )
                if measurement.value < low or measurement.value > high:
                    measurement.classification = "out_of_range"
                else:
                    measurement.classification = "within_range"
            else:
                measurement.classification = "unknown"

            if reference:
                critical_low = reference.critical_low
                critical_high = reference.critical_high
                if critical_low is not None and measurement.value < critical_low:
                    measurement.is_critical = True
                if critical_high is not None and measurement.value > critical_high:
                    measurement.is_critical = True
            if measurement.is_critical:
                measurement.classification = "critical"
                measurement.notes.append("Value crosses configured critical threshold.")

    def _resolve_reference_range(self, measurement: ExamMeasurement) -> Optional[ReferenceRange]:
        key = _normalize_key(measurement.name)
        reference = REFERENCE_RANGES.get(key)
        if not reference:
            return None
        if measurement.unit and _normalize_unit(reference.unit) != measurement.unit:
            measurement.notes.append(
                f"Configured reference unit {reference.unit} differs from measured unit {measurement.unit}."
            )
        return reference


__all__ = ["ExamOCRPipeline", "ExamAnalysis", "ExamMeasurement", "ReferenceRange"]

