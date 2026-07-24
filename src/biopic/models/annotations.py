"""Annotation domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import uuid4


class AnnotationKind(StrEnum):
    """Supported editable scientific annotation object types."""

    TEXT = "text"
    ARROW = "arrow"
    LINE = "line"
    WEDGE = "wedge"
    RECTANGLE = "rectangle"
    ELLIPSE = "ellipse"
    POLYGON = "polygon"
    ASTERISK = "asterisk"


@dataclass(slots=True)
class AnnotationDefinition:
    """Scientific abbreviation or symbol definition."""

    abbreviation: str
    full_definition: str
    category: str = ""
    include_in_legend: bool = True
    notes: str = ""
    id: str = field(default_factory=lambda: str(uuid4()))

    def to_dict(self) -> dict[str, Any]:
        """Serialize the definition."""
        return {
            "id": self.id,
            "abbreviation": self.abbreviation,
            "full_definition": self.full_definition,
            "category": self.category,
            "include_in_legend": self.include_in_legend,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnnotationDefinition:
        """Deserialize the definition."""
        return cls(
            id=str(data["id"]),
            abbreviation=str(data["abbreviation"]),
            full_definition=str(data["full_definition"]),
            category=str(data.get("category", "")),
            include_in_legend=bool(data.get("include_in_legend", True)),
            notes=str(data.get("notes", "")),
        )


@dataclass(slots=True)
class AbbreviationEntry:
    """One abbreviation with language-specific expanded wording."""

    abbreviation: str
    translations: dict[str, str] = field(default_factory=dict)

    def text_for_language(self, language: str) -> str:
        """Return the expansion for the requested language."""
        return self.translations.get(language, "")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the abbreviation entry."""
        return {
            "abbreviation": self.abbreviation,
            "translations": dict(self.translations),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AbbreviationEntry:
        """Deserialize the abbreviation entry."""
        return cls(
            abbreviation=str(data["abbreviation"]),
            translations={
                str(language): str(value)
                for language, value in dict(data.get("translations", {})).items()
            },
        )


@dataclass(slots=True)
class AbbreviationTablePreset:
    """Persistent user-defined abbreviation table preset."""

    name: str
    entries: list[AbbreviationEntry] = field(default_factory=list)
    active_language: str = "English"
    id: str = field(default_factory=lambda: str(uuid4()))
    schema_version: int = 1

    def languages(self) -> list[str]:
        """Return languages defined by this preset."""
        values = {self.active_language}
        for entry in self.entries:
            values.update(language for language, value in entry.translations.items() if value)
        return sorted(values)

    def translated_languages(self) -> list[str]:
        """Return languages with at least one non-empty complete-word entry."""
        values: set[str] = set()
        for entry in self.entries:
            values.update(language for language, value in entry.translations.items() if value)
        return sorted(values)

    def definitions_for_active_language(self) -> list[AnnotationDefinition]:
        """Convert entries to annotation definitions for the active language."""
        return [
            AnnotationDefinition(
                abbreviation=entry.abbreviation,
                full_definition=entry.text_for_language(self.active_language),
            )
            for entry in self.entries
            if entry.abbreviation.strip() and entry.text_for_language(self.active_language).strip()
        ]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the abbreviation table preset."""
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "name": self.name,
            "active_language": self.active_language,
            "entries": [entry.to_dict() for entry in self.entries],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AbbreviationTablePreset:
        """Deserialize the abbreviation table preset."""
        return cls(
            id=str(data["id"]),
            schema_version=int(data.get("schema_version", 1)),
            name=str(data["name"]),
            active_language=str(data.get("active_language", "English")),
            entries=[
                AbbreviationEntry.from_dict(item)
                for item in data.get("entries", [])
            ],
        )


@dataclass(slots=True)
class AnnotationObject:
    """Editable vector annotation in normalized image coordinates."""

    image_node_id: str
    kind: AnnotationKind
    points: list[tuple[float, float]]
    text: str = ""
    definition_id: str | None = None
    category: str = ""
    font: str = "Arial"
    size: float = 12.0
    color: str = "#ffffff"
    line_width: float = 2.0
    fill: str | None = None
    opacity: float = 1.0
    rotation: float = 0.0
    visible: bool = True
    include_in_legend: bool = True
    id: str = field(default_factory=lambda: str(uuid4()))

    def to_dict(self) -> dict[str, Any]:
        """Serialize the annotation object."""
        return {
            "id": self.id,
            "image_node_id": self.image_node_id,
            "kind": self.kind.value,
            "points": [list(point) for point in self.points],
            "text": self.text,
            "definition_id": self.definition_id,
            "category": self.category,
            "font": self.font,
            "size": self.size,
            "color": self.color,
            "line_width": self.line_width,
            "fill": self.fill,
            "opacity": self.opacity,
            "rotation": self.rotation,
            "visible": self.visible,
            "include_in_legend": self.include_in_legend,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnnotationObject:
        """Deserialize the annotation object."""
        points = []
        for point in data.get("points", []):
            if len(point) != 2:
                raise ValueError("annotation points must contain x and y")
            points.append((float(point[0]), float(point[1])))
        return cls(
            id=str(data["id"]),
            image_node_id=str(data["image_node_id"]),
            kind=AnnotationKind(data["kind"]),
            points=points,
            text=str(data.get("text", "")),
            definition_id=data.get("definition_id"),
            category=str(data.get("category", "")),
            font=str(data.get("font", "Arial")),
            size=float(data.get("size", 12.0)),
            color=str(data.get("color", "#ffffff")),
            line_width=float(data.get("line_width", 2.0)),
            fill=data.get("fill"),
            opacity=float(data.get("opacity", 1.0)),
            rotation=float(data.get("rotation", 0.0)),
            visible=bool(data.get("visible", True)),
            include_in_legend=bool(data.get("include_in_legend", True)),
        )


def consolidate_legend(
    definitions: dict[str, AnnotationDefinition],
    annotations: list[AnnotationObject],
    *,
    include_panels: bool = True,
) -> list[str]:
    """Generate legend entries from internal annotation objects."""
    used: dict[str, set[str]] = {}
    for annotation in annotations:
        if (
            not annotation.visible
            or not annotation.include_in_legend
            or annotation.definition_id is None
        ):
            continue
        if annotation.definition_id not in definitions:
            continue
        used.setdefault(annotation.definition_id, set()).add(annotation.image_node_id)
    entries: list[str] = []
    for definition_id in sorted(
        used, key=lambda key: definitions[key].abbreviation.casefold()
    ):
        definition = definitions[definition_id]
        if not definition.include_in_legend:
            continue
        entry = f"{definition.abbreviation}, {definition.full_definition}"
        if include_panels:
            panels = ", ".join(sorted(used[definition_id]))
            entry = f"{entry} ({panels})"
        entries.append(entry)
    return entries
