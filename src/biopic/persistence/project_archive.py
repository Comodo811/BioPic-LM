"""Project save-side asset archive exports."""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from biopic.export.raster import (
    _draw_measurement_overlay,
    export_image,
    export_project_figure_board,
)
from biopic.export.raster_figure_board_rendering import _draw_antialiased_polygon
from biopic.imaging.io import RAW_EXTENSIONS, load_asset_pixels, write_image_metadata
from biopic.imaging.project_render import (
    edit_layers_for_image,
    render_project_image,
)
from biopic.models.annotations import AnnotationKind
from biopic.models.annotations import normalize_wedge_points
from biopic.models.editing import BlendMode, EditLayer, LayerContentKind
from biopic.models.image_asset import ImageAsset, ImageAssetKind
from biopic.models.measurement import ScaleBar
from biopic.models.project import Project

ProjectArchiveProgress = Callable[[Path, str], None]

ENCODABLE_RASTER_FORMATS = ("tiff", "png", "jpeg", "bmp")
COPYABLE_SOURCE_FORMATS = ("preserve_original", "tiff", "png", "jpeg", "bmp")
VIDEO_FORMATS = ("preserve_original",)
DISABLED_FORMAT = "none"
PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)(?::([^{}]+))?\}")
INVALID_FILENAME_CHARS_RE = re.compile(r'[\\/:*?"<>|]+')
MULTIPLE_UNDERSCORES_RE = re.compile(r"_+")
BIOPIC_STAGE_SUFFIXES = (
    "_measured_scaled",
    "_annotated",
    "_unedited",
    "_edited",
    "_stacked",
    "_stitched",
)

DEFAULT_FILENAME_TEMPLATES: dict[str, str] = {
    "original_images": "{original_name}",
    "original_stack_images": "{original_name}",
    "original_video": "{original_name}",
    "stacked_images": "{original_name}_stacked",
    "stitched_images": "{original_name}_stitched",
    "video_stacks": "{original_name}_frame_{frame_index}",
    "unedited_images": "{original_name}_unedited",
    "edited_images": "{original_name}_edited",
    "measured_scaled_images": "{original_name}_measured_scaled",
    "annotated_images": "{original_name}_annotated",
    "figure_board": "{project_name}_figure_board",
}

METADATA_TOKEN_CATEGORIES: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "Taxonomy",
        (
            ("scientific_name", "Species / Scientific name"),
            ("species", "Species"),
            ("genus", "Genus"),
            ("taxonomy", "Taxonomy"),
        ),
    ),
    (
        "Specimen",
        (
            ("specimen_id", "Specimen ID"),
            ("sample_id", "Sample ID"),
            ("voucher_id", "Voucher / Collection ID"),
            ("sex", "Sex"),
            ("life_stage", "Life stage"),
            ("orientation", "View / Orientation"),
            ("body_part", "Body part / Structure"),
            ("side", "Side"),
        ),
    ),
    (
        "Acquisition",
        (
            ("collection_date", "Collection date"),
            ("date", "Date"),
            ("time", "Time"),
            ("magnification", "Magnification"),
            ("objective", "Objective"),
            ("numerical_aperture", "Numerical aperture"),
            ("imaging_method", "Imaging method"),
            ("illumination", "Illumination"),
            ("staining", "Staining / Contrast"),
            ("preparation", "Preparation"),
        ),
    ),
    ("Hardware", (("microscope", "Microscope"), ("camera", "Camera"))),
    (
        "Location / Collector",
        (
            ("collector", "Collector"),
            ("institution", "Institution"),
            ("locality", "Collection locality"),
            ("latitude", "Latitude"),
            ("longitude", "Longitude"),
            ("habitat", "Habitat / Substrate"),
        ),
    ),
    (
        "Image",
        (
            ("width", "Width"),
            ("height", "Height"),
            ("bit_depth", "Bit depth"),
            ("pixel_size", "Pixel size"),
            ("scale", "Scale"),
        ),
    ),
    ("Project", (("project_name", "Project name"), ("project_id", "Project ID"))),
    (
        "Utility",
        (
            ("original_name", "Original name"),
            ("original_extension", "Original extension"),
            ("index", "Index"),
            ("sequence", "Sequence"),
            ("stack_index", "Stack index"),
            ("frame_index", "Frame index"),
        ),
    ),
)
KNOWN_FILENAME_TOKENS = {
    key for _category, fields in METADATA_TOKEN_CATEGORIES for key, _label in fields
}


@dataclass(frozen=True, slots=True)
class SaveStageDefinition:
    """One canonical save stage."""

    key: str
    label: str
    folder: str
    default_enabled: bool
    default_formats: tuple[str, str, str]
    kind: str = "raster"


SAVE_STAGE_DEFINITIONS: tuple[SaveStageDefinition, ...] = (
    SaveStageDefinition(
        "original_images",
        "Save original images into project folder",
        "original_images",
        False,
        ("preserve_original", "none", "none"),
        "source",
    ),
    SaveStageDefinition(
        "original_stack_images",
        "Save original stack images",
        "original_stack_images",
        False,
        ("preserve_original", "none", "none"),
        "source",
    ),
    SaveStageDefinition(
        "original_video",
        "Save original video",
        "original_videos",
        False,
        ("preserve_original", "none", "none"),
        "video",
    ),
    SaveStageDefinition(
        "stacked_images",
        "Save stacked images",
        "stacked_images",
        False,
        ("tiff", "none", "none"),
    ),
    SaveStageDefinition(
        "stitched_images",
        "Save stitched images",
        "stitched_images",
        False,
        ("tiff", "none", "none"),
    ),
    SaveStageDefinition(
        "video_stacks",
        "Save stacks from video",
        "video_stacks",
        False,
        ("tiff", "none", "none"),
    ),
    SaveStageDefinition(
        "unedited_images",
        "Save unedited images",
        "unedited_images",
        False,
        ("tiff", "none", "none"),
    ),
    SaveStageDefinition(
        "edited_images",
        "Save edited images",
        "edited_images",
        True,
        ("tiff", "none", "none"),
    ),
    SaveStageDefinition(
        "measured_scaled_images",
        "Save measured and scaled images",
        "measured_scaled_images",
        False,
        ("tiff", "none", "none"),
    ),
    SaveStageDefinition(
        "annotated_images",
        "Save annotated images",
        "annotated_images",
        True,
        ("tiff", "none", "none"),
    ),
    SaveStageDefinition(
        "figure_board",
        "Save figure board",
        "figure_boards",
        True,
        ("tiff", "none", "none"),
    ),
)
SAVE_STAGE_BY_KEY = {stage.key: stage for stage in SAVE_STAGE_DEFINITIONS}


@dataclass(frozen=True, slots=True)
class SaveStageConfig:
    """Enabled/formats configuration for one stage."""

    enabled: bool = False
    formats: tuple[str, str, str] = ("none", "none", "none")
    filename_template: str = "{original_name}"
    save_caption_text: bool = False
    save_caption_latex: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "formats": list(self.formats),
            "filename_template": self.filename_template,
            "save_caption_text": self.save_caption_text,
            "save_caption_latex": self.save_caption_latex,
        }

    @classmethod
    def from_dict(cls, data: object, definition: SaveStageDefinition) -> SaveStageConfig:
        if not isinstance(data, dict):
            return cls(
                definition.default_enabled,
                definition.default_formats,
                DEFAULT_FILENAME_TEMPLATES.get(definition.key, "{original_name}"),
            )
        formats = data.get("formats", definition.default_formats)
        if not isinstance(formats, list | tuple):
            formats = definition.default_formats
        normalized = _normalize_stage_formats(definition, formats)
        filename_template = str(
            data.get(
                "filename_template",
                DEFAULT_FILENAME_TEMPLATES.get(definition.key, "{original_name}"),
            )
        ).strip()
        return cls(
            enabled=bool(data.get("enabled", definition.default_enabled)),
            formats=normalized,
            filename_template=filename_template
            or DEFAULT_FILENAME_TEMPLATES.get(definition.key, "{original_name}"),
            save_caption_text=bool(data.get("save_caption_text", False)),
            save_caption_latex=bool(data.get("save_caption_latex", False)),
        )

    def unique_formats(self, definition: SaveStageDefinition) -> tuple[str, ...]:
        return _unique_enabled_formats(definition, self.formats)


@dataclass(frozen=True, slots=True)
class SavePreset:
    """Named application-level save preset."""

    name: str
    stages: dict[str, SaveStageConfig] = field(default_factory=dict)

    @classmethod
    def standard(cls) -> SavePreset:
        return cls(
            name="Standard",
            stages={
                definition.key: SaveStageConfig(
                    definition.default_enabled,
                    definition.default_formats,
                    DEFAULT_FILENAME_TEMPLATES.get(definition.key, "{original_name}"),
                )
                for definition in SAVE_STAGE_DEFINITIONS
            },
        )

    def normalized(self) -> SavePreset:
        return SavePreset(
            name=self.name.strip() or "Standard",
            stages={
                definition.key: SaveStageConfig.from_dict(
                    self.stages.get(definition.key, {}).to_dict()
                    if isinstance(self.stages.get(definition.key), SaveStageConfig)
                    else self.stages.get(definition.key),
                    definition,
                )
                for definition in SAVE_STAGE_DEFINITIONS
            },
        )

    def to_dict(self) -> dict[str, object]:
        normalized = self.normalized()
        return {
            "name": normalized.name,
            "stages": {key: value.to_dict() for key, value in normalized.stages.items()},
        }

    @classmethod
    def from_dict(cls, data: object) -> SavePreset:
        if not isinstance(data, dict):
            return cls.standard()
        return cls(
            name=str(data.get("name", "Standard")).strip() or "Standard",
            stages={
                definition.key: SaveStageConfig.from_dict(
                    dict(data.get("stages", {})).get(definition.key),
                    definition,
                )
                for definition in SAVE_STAGE_DEFINITIONS
            },
        ).normalized()


@dataclass(frozen=True, slots=True)
class ProjectSaveOptions:
    """User-configurable project archive save behavior."""

    folder_structure: str = "standard"
    active_preset_name: str = "Standard"
    presets: tuple[SavePreset, ...] = field(default_factory=lambda: (SavePreset.standard(),))
    include_original_images: bool = True
    include_stack_source_images: bool = True
    include_edited_outputs: bool = True
    include_figure_boards: bool = True

    @property
    def active_preset(self) -> SavePreset:
        for preset in self.presets:
            if preset.name == self.active_preset_name:
                return preset.normalized()
        return self.presets[0].normalized() if self.presets else SavePreset.standard()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 4,
            "folder_structure": self.folder_structure,
            "active_preset_name": self.active_preset_name,
            "presets": [preset.to_dict() for preset in self.normalized().presets],
            "include_original_images": self.include_original_images,
            "include_stack_source_images": self.include_stack_source_images,
            "include_edited_outputs": self.include_edited_outputs,
            "include_figure_boards": self.include_figure_boards,
        }

    def normalized(self) -> ProjectSaveOptions:
        presets_by_name: dict[str, SavePreset] = {}
        presets_by_name["Standard"] = SavePreset.standard()
        for preset in self.presets:
            normalized = preset.normalized()
            if normalized.name:
                presets_by_name[normalized.name] = normalized
        active = (
            self.active_preset_name if self.active_preset_name in presets_by_name else "Standard"
        )
        presets = tuple(presets_by_name.values())
        if (
            not self.include_original_images
            or not self.include_stack_source_images
            or not self.include_edited_outputs
            or not self.include_figure_boards
        ):
            adjusted = []
            for preset in presets:
                stages = dict(preset.stages)
                for key in ("original_images", "unedited_images"):
                    if not self.include_original_images and key in stages:
                        stages[key] = SaveStageConfig(
                            False,
                            stages[key].formats,
                            stages[key].filename_template,
                        )
                if not self.include_stack_source_images and "original_stack_images" in stages:
                    stages["original_stack_images"] = SaveStageConfig(
                        False,
                        stages["original_stack_images"].formats,
                        stages["original_stack_images"].filename_template,
                    )
                if not self.include_edited_outputs:
                    for key in ("edited_images", "annotated_images", "measured_scaled_images"):
                        if key in stages:
                            stages[key] = SaveStageConfig(
                                False,
                                stages[key].formats,
                                stages[key].filename_template,
                            )
                if not self.include_figure_boards and "figure_board" in stages:
                    stages["figure_board"] = SaveStageConfig(
                        False,
                        stages["figure_board"].formats,
                        stages["figure_board"].filename_template,
                    )
                adjusted.append(SavePreset(preset.name, stages))
            presets = tuple(adjusted)
        return ProjectSaveOptions(
            folder_structure=self.folder_structure
            if self.folder_structure in {"standard", "flat"}
            else "standard",
            active_preset_name=active,
            presets=presets,
            include_original_images=self.include_original_images,
            include_stack_source_images=self.include_stack_source_images,
            include_edited_outputs=self.include_edited_outputs,
            include_figure_boards=self.include_figure_boards,
        )

    @classmethod
    def from_dict(cls, data: object) -> ProjectSaveOptions:
        if not isinstance(data, dict):
            return cls()
        folder_structure = str(data.get("folder_structure", "standard"))
        if folder_structure not in {"standard", "flat"}:
            folder_structure = "standard"
        schema_version = int(data.get("schema_version", 1) or 1)
        if schema_version < 2 and "presets" not in data:
            return _migrate_legacy_save_options(data, folder_structure)
        presets_data = data.get("presets", [])
        presets = []
        if isinstance(presets_data, list):
            for item in presets_data:
                try:
                    presets.append(SavePreset.from_dict(item))
                except (TypeError, ValueError):
                    continue
        if schema_version < 4:
            presets = [_migrate_v2_standard_save_preset(preset) for preset in presets]
        return cls(
            folder_structure=folder_structure,
            active_preset_name=str(data.get("active_preset_name", "Standard")),
            presets=tuple(presets) or (SavePreset.standard(),),
            include_original_images=bool(data.get("include_original_images", True)),
            include_stack_source_images=bool(data.get("include_stack_source_images", True)),
            include_edited_outputs=bool(data.get("include_edited_outputs", True)),
            include_figure_boards=bool(data.get("include_figure_boards", True)),
    ).normalized()


def _migrate_v2_standard_save_preset(preset: SavePreset) -> SavePreset:
    """Stop legacy Standard settings from exporting every unedited source by default."""
    normalized = preset.normalized()
    if normalized.name != "Standard":
        return normalized
    stages = dict(normalized.stages)
    unedited = stages.get("unedited_images")
    if unedited is not None:
        stages["unedited_images"] = SaveStageConfig(
            False,
            unedited.formats,
            unedited.filename_template,
        )
    return SavePreset(normalized.name, stages).normalized()


def _migrate_legacy_save_options(
    data: dict[str, object],
    folder_structure: str,
) -> ProjectSaveOptions:
    return ProjectSaveOptions(
        folder_structure=folder_structure,
        include_original_images=bool(data.get("include_original_images", True)),
        include_stack_source_images=bool(data.get("include_stack_source_images", True)),
        include_edited_outputs=bool(data.get("include_edited_outputs", True)),
        include_figure_boards=bool(data.get("include_figure_boards", True)),
    ).normalized()


def _normalize_stage_formats(
    definition: SaveStageDefinition,
    formats: object,
) -> tuple[str, str, str]:
    allowed = _allowed_formats(definition)
    values = list(formats) if isinstance(formats, (list, tuple)) else []
    normalized: list[str] = []
    for index in range(3):
        value = _normalize_format_name(
            values[index] if index < len(values) else definition.default_formats[index]
        )
        if value == DISABLED_FORMAT or value in allowed:
            normalized.append(value)
        else:
            normalized.append(DISABLED_FORMAT)
    return normalized[0], normalized[1], normalized[2]


def _unique_enabled_formats(
    definition: SaveStageDefinition,
    formats: tuple[str, str, str],
) -> tuple[str, ...]:
    allowed = _allowed_formats(definition)
    result: list[str] = []
    for fmt in formats:
        if fmt == DISABLED_FORMAT or fmt not in allowed or fmt in result:
            continue
        result.append(fmt)
    if result:
        return tuple(result)
    return tuple(
        dict.fromkeys(
            fmt for fmt in definition.default_formats if fmt != DISABLED_FORMAT and fmt in allowed
        )
    )


def _normalize_format_name(value: object) -> str:
    text = str(value or DISABLED_FORMAT).strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "": DISABLED_FORMAT,
        "disabled": DISABLED_FORMAT,
        "none": DISABLED_FORMAT,
        "preserve": "preserve_original",
        "original": "preserve_original",
        "preserve_original_file": "preserve_original",
        "tif": "tiff",
        "jpg": "jpeg",
    }
    return aliases.get(text, text)


def _allowed_formats(definition: SaveStageDefinition) -> tuple[str, ...]:
    if definition.kind == "source":
        return COPYABLE_SOURCE_FORMATS
    if definition.kind == "video":
        return VIDEO_FORMATS
    return ENCODABLE_RASTER_FORMATS


def _stage_directories(project_dir: Path, options: ProjectSaveOptions) -> dict[str, Path]:
    if options.folder_structure == "flat":
        return {
            definition.key: project_dir / definition.folder for definition in SAVE_STAGE_DEFINITIONS
        }
    return {
        definition.key: project_dir / definition.folder for definition in SAVE_STAGE_DEFINITIONS
    }


def _stage_enabled(preset: SavePreset, stage_key: str) -> bool:
    definition = SAVE_STAGE_BY_KEY[stage_key]
    stage = preset.stages.get(stage_key)
    if stage is None or not stage.enabled:
        return False
    return bool(stage.unique_formats(definition))


@dataclass(frozen=True, slots=True)
class FilenameResolution:
    """Resolved filename stem and non-fatal template warnings."""

    stem: str
    warnings: tuple[str, ...] = ()


def validate_filename_template(template: str) -> tuple[str, ...]:
    """Return unknown placeholder warnings for a filename template."""
    warnings: list[str] = []
    for match in PLACEHOLDER_RE.finditer(template):
        key = match.group(1)
        if key not in KNOWN_FILENAME_TOKENS and f"Unknown metadata field: {key}" not in warnings:
            warnings.append(f"Unknown metadata field: {key}")
    return tuple(warnings)


def resolve_filename_template(
    template: str,
    metadata: dict[str, object] | None = None,
    context: dict[str, object] | None = None,
) -> FilenameResolution:
    """Resolve a safe, non-executable metadata filename template."""
    metadata = metadata or {}
    context = context or {}
    warnings = list(validate_filename_template(template))

    def replacement(match: re.Match[str]) -> str:
        key = match.group(1)
        modifier = match.group(2)
        if key not in KNOWN_FILENAME_TOKENS:
            return "unknown"
        value = context.get(key, metadata.get(key))
        if value in {None, ""} and key == "species":
            value = metadata.get("scientific_name")
        if value in {None, ""}:
            value = "unknown"
        return _sanitize_filename_token(_format_filename_token(value, modifier))

    resolved = PLACEHOLDER_RE.sub(replacement, template.strip())
    return FilenameResolution(_sanitize_filename_stem(resolved), tuple(warnings))


def _format_filename_token(value: object, modifier: str | None) -> str:
    if modifier and modifier.endswith("d"):
        width_text = modifier[:-1]
        if width_text.isdigit():
            with suppress(TypeError, ValueError):
                return f"{int(value):0{int(width_text)}d}"
    return str(value)


def _sanitize_filename_token(value: str) -> str:
    text = INVALID_FILENAME_CHARS_RE.sub("_", value.strip())
    text = re.sub(r"\s+", "_", text)
    text = text.replace(".", "_")
    return MULTIPLE_UNDERSCORES_RE.sub("_", text).strip(" _.") or "unknown"


def _sanitize_filename_stem(value: str) -> str:
    text = INVALID_FILENAME_CHARS_RE.sub("_", value.strip())
    text = text.replace("/", "_").replace("\\", "_")
    text = re.sub(r"\s+", "_", text)
    text = MULTIPLE_UNDERSCORES_RE.sub("_", text)
    text = text.strip(" ._")
    while ".." in text:
        text = text.replace("..", "_")
    return text or "untitled"


def _canonical_original_stem(stem: str) -> str:
    """Return the stable source stem before BioPic stage suffixes were appended."""
    text = _sanitize_filename_stem(stem)
    changed = True
    while changed:
        changed = False
        for suffix in BIOPIC_STAGE_SUFFIXES:
            if text.endswith(suffix) and len(text) > len(suffix):
                text = text[: -len(suffix)]
                changed = True
                break
    return text or _sanitize_filename_stem(stem)


def _cleanup_compounded_stage_outputs(
    output_dir: Path,
    current_path: Path,
    definition: SaveStageDefinition,
) -> None:
    """Remove older outputs whose names contain repeated BioPic stage suffixes."""
    stage_suffix = f"_{definition.key.removesuffix('_images')}"
    if definition.key == "measured_scaled_images":
        stage_suffix = "_measured_scaled"
    elif definition.key in {"original_images", "original_stack_images", "original_video"}:
        return
    current_stem = current_path.stem
    current_base = _canonical_original_stem(current_stem)
    if not current_base:
        return
    for candidate in output_dir.glob(f"*{current_path.suffix}"):
        if candidate == current_path or not candidate.is_file():
            continue
        candidate_stem = candidate.stem
        if not candidate_stem.endswith(stage_suffix):
            continue
        if candidate_stem == current_stem:
            continue
        if _canonical_original_stem(candidate_stem) != current_base:
            continue
        try:
            candidate.unlink()
        except OSError:
            continue
        _remove_signature_for_output(candidate)


def _filename_context(
    project: Project,
    asset: ImageAsset | None = None,
    source_path: Path | None = None,
    sequence: int = 1,
    frame_index: int | None = None,
    stack_index: int | None = None,
) -> dict[str, object]:
    original_path = source_path or (Path(asset.path) if asset is not None else Path("item"))
    display_path = Path(asset.filename) if asset is not None else original_path
    stable_original = _canonical_original_stem(display_path.stem or original_path.stem)
    return {
        "project_name": project.name,
        "project_id": project.id,
        "original_name": stable_original,
        "original_extension": display_path.suffix.lstrip(".") or original_path.suffix.lstrip("."),
        "index": f"{sequence:03d}",
        "sequence": f"{sequence:03d}",
        "stack_index": f"{(stack_index or sequence):03d}",
        "frame_index": f"{(frame_index or sequence):06d}",
        "width": asset.width if asset is not None else "",
        "height": asset.height if asset is not None else "",
        "bit_depth": asset.dtype if asset is not None else "",
    }


def _resolved_output_path(
    output_dir: Path,
    config: SaveStageConfig,
    fmt: str,
    *,
    project: Project,
    asset: ImageAsset | None,
    source_path: Path | None,
    sequence: int,
    used_paths: set[Path],
    extension: str | None = None,
) -> Path:
    context = _filename_context(project, asset, source_path, sequence)
    metadata = asset.metadata if asset is not None else {}
    stem = resolve_filename_template(config.filename_template, metadata, context).stem
    suffix = extension or f".{_extension_for_format(fmt)}"
    candidate = output_dir / f"{stem}{suffix}"
    if candidate not in used_paths:
        used_paths.add(candidate)
        return candidate
    index = 2
    while True:
        candidate = output_dir / f"{stem}_{index:03d}{suffix}"
        if candidate not in used_paths:
            used_paths.add(candidate)
            return candidate
        index += 1


def _source_stage_for_asset(asset: ImageAsset) -> str:
    if asset.kind is ImageAssetKind.STACK_SOURCE:
        return "original_stack_images"
    return "original_images"


def _archive_source_asset(
    project: Project,
    asset: ImageAsset,
    source_path: Path,
    output_dir: Path,
    config: SaveStageConfig,
    definition: SaveStageDefinition,
    sequence: int,
    used_paths: set[Path],
) -> Path:
    source_is_raw = source_path.suffix.lower() in RAW_EXTENSIONS
    outputs = [
        _save_source_file(
            project,
            asset,
            source_path,
            output_dir,
            config,
            fmt,
            "source",
            sequence,
            used_paths,
        )
        for fmt in config.unique_formats(definition)
        if fmt == "preserve_original" or not source_is_raw
    ]
    return outputs[0] if outputs else source_path


def _save_asset_pixels(
    project: Project,
    asset: ImageAsset,
    source_path: Path,
    output_dir: Path,
    config: SaveStageConfig,
    definition: SaveStageDefinition,
    *,
    suffix_label: str,
    sequence: int,
    used_paths: set[Path],
    progress: ProjectArchiveProgress | None,
    action: str,
) -> Path | None:
    if source_path.suffix.lower() in RAW_EXTENSIONS:
        return None
    pixels: np.ndarray | None = None
    first_output: Path | None = None
    for fmt in config.unique_formats(definition):
        destination = _source_output_path(
            project,
            asset,
            source_path,
            output_dir,
            config,
            fmt,
            suffix_label,
            sequence,
            used_paths,
        )
        first_output = first_output or destination
        signature = _source_archive_signature(asset, source_path) | {
            "format": fmt,
            "suffix_label": suffix_label,
        }
        if _output_is_current(destination, signature):
            _notify_archive_progress(progress, destination, f"Checking {suffix_label} image")
            continue
        try:
            if source_path.resolve() == destination.resolve():
                _write_output_signature(destination, signature)
                _notify_archive_progress(progress, destination, action)
                continue
        except OSError:
            pass
        if fmt == "preserve_original":
            output_dir.mkdir(parents=True, exist_ok=True)
            try:
                if source_path.resolve() != destination.resolve():
                    shutil.copy2(source_path, destination)
            except FileNotFoundError:
                continue
            _try_write_archived_image_metadata(destination, asset.metadata)
            _write_output_signature(destination, signature)
        else:
            if pixels is None:
                pixels = load_asset_pixels(asset)
            export_image(pixels, destination, metadata=asset.metadata)
            _write_output_signature(destination, signature)
        _cleanup_compounded_stage_outputs(output_dir, destination, definition)
        _notify_archive_progress(progress, destination, action)
    return first_output


def _save_source_file(
    project: Project,
    asset: ImageAsset,
    source_path: Path,
    output_dir: Path,
    config: SaveStageConfig,
    fmt: str,
    suffix_label: str,
    sequence: int,
    used_paths: set[Path],
) -> Path:
    destination = _source_output_path(
        project,
        asset,
        source_path,
        output_dir,
        config,
        fmt,
        suffix_label,
        sequence,
        used_paths,
    )
    signature = _source_archive_signature(asset, source_path) | {
        "format": fmt,
        "suffix_label": suffix_label,
    }
    if _output_is_current(destination, signature):
        return destination
    output_dir.mkdir(parents=True, exist_ok=True)
    if fmt == "preserve_original":
        try:
            if source_path.resolve() != destination.resolve():
                shutil.copy2(source_path, destination)
        except FileNotFoundError:
            return source_path
    else:
        pixels = load_asset_pixels(asset)
        export_image(pixels, destination, metadata=asset.metadata)
    if fmt == "preserve_original":
        _try_write_archived_image_metadata(destination, asset.metadata)
    _write_output_signature(destination, signature)
    return destination


def _source_output_path(
    project: Project,
    asset: ImageAsset,
    source_path: Path,
    output_dir: Path,
    config: SaveStageConfig,
    fmt: str,
    suffix_label: str,
    sequence: int,
    used_paths: set[Path],
) -> Path:
    if fmt == "preserve_original":
        extension = source_path.suffix or ".bin"
    else:
        extension = f".{_extension_for_format(fmt)}"
    return _resolved_output_path(
        output_dir,
        config,
        fmt,
        project=project,
        asset=asset,
        source_path=source_path,
        sequence=sequence,
        used_paths=used_paths,
        extension=extension,
    )


def _save_project_raster_stage(
    project: Project,
    asset: ImageAsset,
    node_id: str,
    output_dir: Path,
    config: SaveStageConfig,
    definition: SaveStageDefinition,
    suffix_label: str,
    include_overlays: bool,
    sequence: int,
    used_paths: set[Path],
    progress: ProjectArchiveProgress | None,
) -> None:
    rendered: np.ndarray | None = None
    signature = _raster_stage_output_signature(project, node_id, definition.key) | {
        "stage": definition.key,
        "suffix_label": suffix_label,
        "include_overlays": include_overlays,
    }
    for fmt in config.unique_formats(definition):
        path = _resolved_output_path(
            output_dir,
            config,
            fmt,
            project=project,
            asset=asset,
            source_path=Path(asset.path),
            sequence=sequence,
            used_paths=used_paths,
        )
        fmt_signature = signature | {"format": fmt}
        if _output_is_current(path, fmt_signature):
            _cleanup_compounded_stage_outputs(output_dir, path, definition)
            _notify_archive_progress(progress, path, f"Checking {suffix_label} image")
            continue
        if rendered is None:
            rendered = render_project_image(project, node_id)
            if rendered is None:
                return
            if include_overlays:
                rendered = _render_measurements_and_annotations(project, node_id, rendered)
        export_image(rendered, path, metadata=asset.metadata)
        _write_output_signature(path, fmt_signature)
        _cleanup_compounded_stage_outputs(output_dir, path, definition)
        _notify_archive_progress(progress, path, f"Saving {suffix_label} image")


def _node_has_measurements_or_scale(project: Project, node_id: str) -> bool:
    return any(
        scale_bar.image_node_id == node_id for scale_bar in project.scale_bars.values()
    ) or any(measurement.image_node_id == node_id for measurement in project.measurements.values())


def _node_has_annotations(project: Project, node_id: str) -> bool:
    return any(annotation.image_node_id == node_id for annotation in project.annotations.values())


def _project_video_paths(project: Project) -> list[Path]:
    paths: list[Path] = []
    for stack in project.stacks.values():
        value = stack.metadata.get("source_video_path") or stack.metadata.get("source_video")
        if isinstance(value, str) and value:
            paths.append(Path(value))
    for asset in project.assets.values():
        value = asset.metadata.get("source_video_path") or asset.metadata.get("source_video")
        if isinstance(value, str) and value:
            paths.append(Path(value))
    return list({str(path): path for path in paths}.values())


def _copy_original_video(
    project: Project,
    video_path: Path,
    output_dir: Path,
    config: SaveStageConfig,
    sequence: int,
    used_paths: set[Path],
    progress: ProjectArchiveProgress | None,
) -> None:
    if not config.enabled:
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = _resolved_output_path(
        output_dir,
        config,
        "preserve_original",
        project=project,
        asset=None,
        source_path=video_path,
        sequence=sequence,
        used_paths=used_paths,
        extension=video_path.suffix or ".video",
    )
    signature = {"kind": "video", "source": str(video_path)}
    if _output_is_current(destination, signature):
        _notify_archive_progress(progress, destination, "Checking original video")
        return
    shutil.copy2(video_path, destination)
    _write_output_signature(destination, signature)
    _notify_archive_progress(progress, destination, "Saving original video")


def _unique_output_path(output_dir: Path, stem: str, fmt: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"{stem}.{_extension_for_format(fmt)}"


def _extension_for_format(fmt: str) -> str:
    if fmt in {"tif", "tiff"}:
        return "tif"
    if fmt == "jpeg":
        return "jpg"
    return fmt


def export_project_archive(
    project: Project,
    manifest_path: Path,
    options: ProjectSaveOptions | None = None,
    progress: ProjectArchiveProgress | None = None,
) -> dict[str, str]:
    """Create/update the project folder next to a saved manifest."""
    options = (options or ProjectSaveOptions()).normalized()
    preset = options.active_preset
    project_dir = project_folder_for_manifest(manifest_path)
    stage_dirs = _stage_directories(project_dir, options)
    _cleanup_visible_archive_sidecars(
        set(stage_dirs.values())
        | {project_dir / "unedited", project_dir / "edited", project_dir / "figure_boards"}
    )
    used_paths: set[Path] = set()

    archived_paths: dict[str, str] = {}
    for sequence, asset in enumerate(project.assets.values(), start=1):
        source_path = _asset_source_path(asset, manifest_path)
        archive_source_stage = _source_stage_for_asset(asset)
        if source_path.exists() and _stage_enabled(preset, archive_source_stage):
            archived = _archive_source_asset(
                project,
                asset,
                source_path,
                stage_dirs[archive_source_stage],
                preset.stages[archive_source_stage],
                SAVE_STAGE_BY_KEY[archive_source_stage],
                sequence,
                used_paths,
            )
            archived_paths[asset.id] = str(archived)
            _notify_archive_progress(progress, Path(archived), "Saving source image")
        else:
            archived_paths[asset.id] = asset.path

        if (
            source_path.exists()
            and _stage_enabled(preset, "unedited_images")
            and asset.kind is not ImageAssetKind.STACK_SOURCE
        ):
            unedited_path = _save_asset_pixels(
                project,
                asset,
                source_path,
                stage_dirs["unedited_images"],
                preset.stages["unedited_images"],
                SAVE_STAGE_BY_KEY["unedited_images"],
                suffix_label="unedited",
                sequence=sequence,
                used_paths=used_paths,
                progress=progress,
                action="Saving unedited image",
            )
            if unedited_path is not None and archived_paths[asset.id] == asset.path:
                archived_paths[asset.id] = str(unedited_path)

        node_id = project.source_node_id_for_asset(asset.id)
        if node_id is None:
            continue
        if _stage_enabled(preset, "stacked_images") and asset.kind is ImageAssetKind.STACK_RESULT:
            _save_project_raster_stage(
                project,
                asset,
                node_id,
                stage_dirs["stacked_images"],
                preset.stages["stacked_images"],
                SAVE_STAGE_BY_KEY["stacked_images"],
                "stacked",
                False,
                sequence,
                used_paths,
                progress,
            )
        if (
            _stage_enabled(preset, "stitched_images")
            and asset.kind is ImageAssetKind.EDIT_DERIVATIVE
        ):
            _save_project_raster_stage(
                project,
                asset,
                node_id,
                stage_dirs["stitched_images"],
                preset.stages["stitched_images"],
                SAVE_STAGE_BY_KEY["stitched_images"],
                "stitched",
                False,
                sequence,
                used_paths,
                progress,
            )
        if _stage_enabled(preset, "edited_images") and _node_has_saved_outputs(project, node_id):
            _save_project_raster_stage(
                project,
                asset,
                node_id,
                stage_dirs["edited_images"],
                preset.stages["edited_images"],
                SAVE_STAGE_BY_KEY["edited_images"],
                "edited",
                False,
                sequence,
                used_paths,
                progress,
            )
        if _stage_enabled(preset, "measured_scaled_images") and _node_has_measurements_or_scale(
            project, node_id
        ):
            _save_project_raster_stage(
                project,
                asset,
                node_id,
                stage_dirs["measured_scaled_images"],
                preset.stages["measured_scaled_images"],
                SAVE_STAGE_BY_KEY["measured_scaled_images"],
                "measured_scaled",
                True,
                sequence,
                used_paths,
                progress,
            )
        if _stage_enabled(preset, "annotated_images") and _node_has_annotations(
            project, node_id
        ):
            _save_project_raster_stage(
                project,
                asset,
                node_id,
                stage_dirs["annotated_images"],
                preset.stages["annotated_images"],
                SAVE_STAGE_BY_KEY["annotated_images"],
                "annotated",
                True,
                sequence,
                used_paths,
                progress,
            )

    if _stage_enabled(preset, "original_video"):
        for sequence, video_path in enumerate(_project_video_paths(project), start=1):
            if video_path.exists():
                _copy_original_video(
                    project,
                    video_path,
                    stage_dirs["original_video"],
                    preset.stages["original_video"],
                    sequence,
                    used_paths,
                    progress,
                )

    if _stage_enabled(preset, "video_stacks"):
        for sequence, asset in enumerate(project.assets.values(), start=1):
            if asset.metadata.get("source_video"):
                source_path = _asset_source_path(asset, manifest_path)
                if source_path.exists():
                    _save_asset_pixels(
                        project,
                        asset,
                        source_path,
                        stage_dirs["video_stacks"],
                        preset.stages["video_stacks"],
                        SAVE_STAGE_BY_KEY["video_stacks"],
                        suffix_label="video_stack",
                        sequence=sequence,
                        used_paths=used_paths,
                        progress=progress,
                        action="Saving video stack frame",
                    )

    if _stage_enabled(preset, "figure_board"):
        for sequence, board in enumerate(project.figure_boards.values(), start=1):
            signature = _board_output_signature(project, board.id)
            for fmt in preset.stages["figure_board"].unique_formats(
                SAVE_STAGE_BY_KEY["figure_board"]
            ):
                figure_config = preset.stages["figure_board"]
                board_path = _resolved_output_path(
                    stage_dirs["figure_board"],
                    figure_config,
                    fmt,
                    project=project,
                    asset=None,
                    source_path=Path(board.name or board.id),
                    sequence=sequence,
                    used_paths=used_paths,
                )
                signature = signature | {
                    "save_caption_text": figure_config.save_caption_text,
                    "save_caption_latex": figure_config.save_caption_latex,
                }
                if _output_is_current(board_path, signature):
                    _notify_archive_progress(progress, board_path, "Checking figure board")
                    continue
                export_project_figure_board(
                    project,
                    board,
                    board_path,
                    save_caption_text=figure_config.save_caption_text,
                    save_caption_latex=figure_config.save_caption_latex,
                )
                _write_output_signature(board_path, signature)
                _notify_archive_progress(progress, board_path, "Saving figure board")
    return archived_paths


def project_archive_step_count(
    project: Project,
    manifest_path: Path,
    options: ProjectSaveOptions | None = None,
) -> int:
    """Return the number of archive progress units a project save will report."""
    options = (options or ProjectSaveOptions()).normalized()
    preset = options.active_preset
    count = 0
    for asset in project.assets.values():
        if _stage_enabled(preset, _source_stage_for_asset(asset)):
            source_path = _asset_source_path(asset, manifest_path)
            if source_path.exists():
                count += 1
        node_id = project.source_node_id_for_asset(asset.id)
        if (
            _stage_enabled(preset, "unedited_images")
            and asset.kind is not ImageAssetKind.STACK_SOURCE
        ):
            count += _raster_progress_count(
                preset.stages["unedited_images"],
                SAVE_STAGE_BY_KEY["unedited_images"],
                _asset_source_path(asset, manifest_path),
            )
        if (
            node_id is not None
            and _stage_enabled(preset, "edited_images")
            and _node_has_saved_outputs(project, node_id)
        ):
            count += len(
                preset.stages["edited_images"].unique_formats(SAVE_STAGE_BY_KEY["edited_images"])
            )
        if (
            node_id is not None
            and _stage_enabled(preset, "annotated_images")
            and _node_has_annotations(project, node_id)
        ):
            count += len(
                preset.stages["annotated_images"].unique_formats(
                    SAVE_STAGE_BY_KEY["annotated_images"]
                )
            )
        if (
            node_id is not None
            and _stage_enabled(preset, "measured_scaled_images")
            and _node_has_measurements_or_scale(project, node_id)
        ):
            count += len(
                preset.stages["measured_scaled_images"].unique_formats(
                    SAVE_STAGE_BY_KEY["measured_scaled_images"]
                )
            )
    if _stage_enabled(preset, "figure_board"):
        count += len(project.figure_boards) * len(
            preset.stages["figure_board"].unique_formats(SAVE_STAGE_BY_KEY["figure_board"])
        )
    return count


def _raster_progress_count(
    config: SaveStageConfig,
    definition: SaveStageDefinition,
    source_path: Path,
) -> int:
    if source_path.suffix.lower() in RAW_EXTENSIONS:
        return 0
    return len(config.unique_formats(definition))


def project_folder_for_manifest(manifest_path: Path) -> Path:
    """Return the sibling folder used for project-owned assets."""
    name = manifest_path.name
    if name.endswith(".biopic.json"):
        folder_name = name[: -len(".biopic.json")]
    else:
        folder_name = manifest_path.stem
    return manifest_path.with_name(folder_name)


def relative_project_path(path: Path, manifest_path: Path) -> str:
    """Return a portable path relative to the manifest when possible."""
    try:
        return path.resolve().relative_to(manifest_path.parent.resolve()).as_posix()
    except ValueError:
        return str(path)


def _asset_source_path(asset: ImageAsset, manifest_path: Path) -> Path:
    path = Path(asset.path)
    if path.is_absolute():
        return path
    return manifest_path.parent / path


def _archive_unedited_asset(asset: ImageAsset, source_path: Path, unedited_dir: Path) -> Path:
    suffix = source_path.suffix or ".tif"
    destination = unedited_dir / f"{_asset_stem(asset)}__source{suffix}"
    signature = _source_archive_signature(asset, source_path)
    if _output_is_current(destination, signature):
        return destination
    try:
        source_is_destination = source_path.resolve() == destination.resolve()
        if not source_is_destination:
            shutil.copy2(source_path, destination)
    except FileNotFoundError:
        return source_path
    if not source_is_destination:
        _try_write_archived_image_metadata(destination, asset.metadata)
    _write_output_signature(destination, signature)
    return destination


def _try_write_archived_image_metadata(path: Path, metadata: dict[str, object]) -> None:
    with suppress(OSError, TypeError, ValueError):
        write_image_metadata(path, metadata)


def _should_archive_unedited_asset(asset: ImageAsset, options: ProjectSaveOptions) -> bool:
    if not options.include_original_images:
        return False
    return asset.kind is not ImageAssetKind.STACK_SOURCE or options.include_stack_source_images


def _notify_archive_progress(
    progress: ProjectArchiveProgress | None,
    path: Path,
    action: str,
) -> None:
    if progress is not None:
        progress(path, action)


def _source_archive_signature(asset: ImageAsset, source_path: Path) -> dict[str, object]:
    try:
        stat = source_path.stat()
        source_snapshot: dict[str, object] = {
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }
    except FileNotFoundError:
        source_snapshot = {"missing": True}
    return {
        "kind": "source",
        "asset_id": asset.id,
        "source": str(source_path),
        "source_snapshot": source_snapshot,
        "metadata": asset.metadata,
    }


def _raster_stage_output_signature(
    project: Project,
    node_id: str,
    stage_key: str,
) -> dict[str, object]:
    signature = _edited_output_signature(project, node_id)
    if stage_key in {"measured_scaled_images", "annotated_images"}:
        signature["measure_scale"] = _measure_scale_signature(project, node_id)
    if stage_key == "annotated_images":
        signature["annotations"] = _annotation_signature(project, node_id)
    return signature


def _edited_output_signature(project: Project, node_id: str) -> dict[str, object]:
    return {
        "kind": "edited",
        "node_id": node_id,
        "source": _source_image_signature(project, node_id),
        "edit_layers": [
            layer.to_dict() for layer in edit_layers_for_image(project, node_id)
        ],
        "adjustment_layers": [
            layer.to_dict() for layer in project.adjustment_layers_for_image(node_id)
        ],
    }


def _source_image_signature(project: Project, node_id: str) -> dict[str, object]:
    node = project.graph.nodes.get(node_id)
    asset_id = node.parameters.get("asset_id") if node is not None else None
    asset = project.assets.get(asset_id) if isinstance(asset_id, str) else None
    if asset is None:
        return {"missing": node_id}
    return {
        "asset_id": asset.id,
        "checksum": asset.checksum,
        "width": asset.width,
        "height": asset.height,
        "frames": asset.frames,
        "dtype": asset.dtype,
        "color_model": asset.color_model,
        "filename": asset.filename,
        "metadata": asset.metadata,
    }


def _measure_scale_signature(project: Project, node_id: str) -> dict[str, object]:
    return {
        "calibration": (
            project.calibrations[node_id].to_dict()
            if node_id in project.calibrations
            else None
        ),
        "scale_bars": [
            scale_bar.to_dict()
            for scale_bar in project.scale_bars.values()
            if scale_bar.image_node_id == node_id
        ],
        "measurements": [
            measurement.to_dict()
            for measurement in project.measurements.values()
            if measurement.image_node_id == node_id
        ],
    }


def _annotation_signature(project: Project, node_id: str) -> dict[str, object]:
    annotations = [
        annotation
        for annotation in project.annotations.values()
        if annotation.image_node_id == node_id
    ]
    definition_ids = {
        annotation.definition_id for annotation in annotations if annotation.definition_id
    }
    return {
        "annotations": [annotation.to_dict() for annotation in annotations],
        "definitions": [
            definition.to_dict()
            for definition in project.annotation_definitions.values()
            if definition.id in definition_ids
        ],
    }


def _board_output_signature(project: Project, board_id: str) -> dict[str, object]:
    board = project.figure_boards.get(board_id)
    if board is None:
        board = next(
            item for item in project.figure_boards.values() if item.id == board_id
        )
    source_signatures = {
        panel.source_node_id: _raster_stage_output_signature(
            project,
            panel.source_node_id,
            "annotated_images",
        )
        for panel in board.panels
        if panel.source_node_id is not None
    }
    return {
        "kind": "figure_board",
        "board": board.to_dict(),
        "sources": source_signatures,
    }

def _output_is_current(path: Path, signature: dict[str, object]) -> bool:
    if not path.exists():
        return False
    signature_path = _signature_path(path)
    try:
        current = json.loads(signature_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return current == signature


def _write_output_signature(path: Path, signature: dict[str, object]) -> None:
    _write_json_if_changed(_signature_path(path), signature)


def _remove_signature_for_output(path: Path) -> None:
    with suppress(OSError):
        _signature_path(path).unlink()


def _signature_path(path: Path) -> Path:
    root = _archive_root_for_output(path)
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        relative = path.name
    digest = sha256(relative.encode("utf-8")).hexdigest()[:16]
    signature_dir = root / ".biopic_cache" / "signatures"
    return signature_dir / f"{_safe_name(path.stem)}_{digest}.json"


def _archive_root_for_output(path: Path) -> Path:
    parent = path.parent
    stage_folder_names = {definition.folder for definition in SAVE_STAGE_DEFINITIONS}
    if parent.name in stage_folder_names | {"unedited", "edited"}:
        return parent.parent
    return parent


def _cleanup_visible_archive_sidecars(directories: set[Path]) -> None:
    for directory in directories:
        if not directory.exists():
            continue
        for pattern in ("*__metadata.json", "*.signature.json"):
            for path in directory.glob(pattern):
                try:
                    if path.is_file():
                        path.unlink()
                except OSError:
                    pass


def _write_json_if_changed(path: Path, payload: dict[str, object]) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True)
    try:
        if path.read_text(encoding="utf-8") == text:
            return
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")


def _node_has_saved_outputs(project: Project, node_id: str) -> bool:
    return any(
        layer.enabled and layer.opacity > 0.0
        for layer in project.adjustment_layers_for_image(node_id)
    ) or any(_edit_layer_changes_output(layer) for layer in edit_layers_for_image(project, node_id))


def _edit_layer_changes_output(layer: EditLayer) -> bool:
    """Return whether a stored edit layer represents a user-visible edited output."""
    if (
        layer.content_kind is LayerContentKind.EMPTY
        and layer.content is None
        and layer.alpha is None
    ):
        return False
    is_plain_source_layer = (
        layer.content_kind is LayerContentKind.SOURCE
        and layer.content is None
        and layer.alpha is None
        and layer.mask_content is None
        and layer.mask_node_id is None
        and layer.filter_operation is None
    )
    if not is_plain_source_layer:
        return True
    if layer.name == "Original Image" and not layer.visible:
        return False
    return not (
        layer.visible
        and abs(layer.opacity - 1.0) <= 1e-9
        and layer.blend_mode is BlendMode.NORMAL
        and layer.offset_x == 0
        and layer.offset_y == 0
    )


def _node_has_raster_overlays(project: Project, node_id: str) -> bool:
    return any(
        scale_bar.image_node_id == node_id for scale_bar in project.scale_bars.values()
    ) or any(annotation.image_node_id == node_id for annotation in project.annotations.values())


def _render_measurements_and_annotations(
    project: Project,
    node_id: str,
    pixels: np.ndarray,
) -> np.ndarray:
    display = _display_compatible(pixels)
    image = Image.fromarray(display).convert("RGBA")
    draw = ImageDraw.Draw(image, "RGBA")
    for scale_bar in project.scale_bars.values():
        if scale_bar.image_node_id == node_id:
            _draw_scale_bar(draw, image.size, scale_bar)
    for annotation in project.annotations.values():
        if annotation.image_node_id == node_id and annotation.visible:
            _draw_annotation(image, draw, image.size, annotation)
    for measurement in project.measurements.values():
        if measurement.image_node_id == node_id:
            _draw_measurement_overlay(draw, image.size, measurement)
    return np.asarray(image.convert("RGB"))


def _draw_scale_bar(
    draw: ImageDraw.ImageDraw,
    image_size: tuple[int, int],
    scale_bar: ScaleBar,
) -> None:
    width, height = image_size
    length = max(1.0, float(scale_bar.pixel_length))
    thickness = max(1.0, float(scale_bar.width_px))
    is_vertical = scale_bar.orientation == "vertical"
    bar_width = thickness if is_vertical else length
    bar_height = length if is_vertical else thickness
    x, y = _scale_bar_origin(scale_bar, float(width), float(height), bar_width, bar_height)
    if scale_bar.background:
        pad = max(4.0, thickness * 2.0)
        draw.rectangle(
            (x - pad, y - pad, x + bar_width + pad, y + bar_height + pad),
            fill=_rgba(scale_bar.background, scale_bar.opacity),
        )
    color = _rgba(scale_bar.foreground, scale_bar.opacity)
    if is_vertical:
        draw.line(
            (x + thickness / 2.0, y, x + thickness / 2.0, y + length),
            fill=color,
            width=int(round(thickness)),
        )
    else:
        draw.line(
            (x, y + thickness / 2.0, x + length, y + thickness / 2.0),
            fill=color,
            width=int(round(thickness)),
        )
    if scale_bar.display_length:
        text = f"{scale_bar.physical_length:g} {scale_bar.unit}"
        font = _font(scale_bar.font_size)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        if is_vertical:
            text_xy = (x + thickness + 6.0, y + length / 2.0)
        else:
            text_xy = (x + length / 2.0 - text_width / 2.0, y + thickness + 4.0)
        draw.text(text_xy, text, fill=color, font=font)


def _draw_annotation(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    image_size: tuple[int, int],
    annotation: object,
) -> None:
    width, height = image_size
    annotation_points = (
        normalize_wedge_points(list(annotation.points))
        if annotation.kind is AnnotationKind.WEDGE
        else annotation.points
    )
    points = [(float(x) * width, float(y) * height) for x, y in annotation_points]
    if not points:
        return
    color = _rgba(annotation.color, annotation.opacity)
    if annotation.kind is AnnotationKind.TEXT:
        draw.text(points[0], annotation.text or "Label", fill=color, font=_font(annotation.size))
        return
    if len(points) < 2:
        return
    line_width = max(1, int(round(annotation.line_width)))
    if annotation.kind is AnnotationKind.WEDGE and len(points) >= 2:
        fill = _rgba(annotation.fill or annotation.color, annotation.opacity)
        _draw_antialiased_polygon(image, _normal_wedge_triangle(points, 0.0), fill)
        return
    draw.line(points, fill=color, width=line_width, joint="curve")
    if annotation.kind is AnnotationKind.ARROW:
        _draw_arrow_head(draw, points[-2], points[-1], color, line_width)


def _normal_wedge_triangle(
    points: list[tuple[float, float]],
    minimum_base_width: float,
) -> list[tuple[float, float]]:
    if len(points) == 2:
        base_mid = points[0]
        tip = points[1]
        axis_x = tip[0] - base_mid[0]
        axis_y = tip[1] - base_mid[1]
        axis_length = max(1.0, (axis_x * axis_x + axis_y * axis_y) ** 0.5)
        perp_x = -axis_y / axis_length
        perp_y = axis_x / axis_length
        half = max(minimum_base_width / 2.0, axis_length * 0.22, 0.5)
        return [
            tip,
            (base_mid[0] - perp_x * half, base_mid[1] - perp_y * half),
            (base_mid[0] + perp_x * half, base_mid[1] + perp_y * half),
        ]
    tip = points[0]
    base_a = points[1]
    base_b = points[2]
    base_mid = ((base_a[0] + base_b[0]) / 2.0, (base_a[1] + base_b[1]) / 2.0)
    dx = base_b[0] - base_a[0]
    dy = base_b[1] - base_a[1]
    base_width = (dx * dx + dy * dy) ** 0.5
    if base_width >= minimum_base_width:
        return [tip, base_a, base_b]
    axis_x = tip[0] - base_mid[0]
    axis_y = tip[1] - base_mid[1]
    axis_length = max(1.0, (axis_x * axis_x + axis_y * axis_y) ** 0.5)
    perp_x = -axis_y / axis_length
    perp_y = axis_x / axis_length
    half = max(minimum_base_width / 2.0, 0.5)
    return [
        tip,
        (base_mid[0] - perp_x * half, base_mid[1] - perp_y * half),
        (base_mid[0] + perp_x * half, base_mid[1] + perp_y * half),
    ]


def _draw_arrow_head(
    draw: ImageDraw.ImageDraw,
    start: tuple[float, float],
    end: tuple[float, float],
    color: tuple[int, int, int, int],
    line_width: int,
) -> None:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = max(1.0, (dx * dx + dy * dy) ** 0.5)
    ux = dx / length
    uy = dy / length
    nx = -uy
    ny = ux
    head = max(8.0, line_width * 5.0)
    back = (end[0] - ux * head, end[1] - uy * head)
    draw.line(
        (end, (back[0] + nx * head * 0.45, back[1] + ny * head * 0.45)),
        fill=color,
        width=line_width,
    )
    draw.line(
        (end, (back[0] - nx * head * 0.45, back[1] - ny * head * 0.45)),
        fill=color,
        width=line_width,
    )


def _scale_bar_origin(
    scale_bar: ScaleBar,
    image_width: float,
    image_height: float,
    bar_width: float,
    bar_height: float,
) -> tuple[float, float]:
    offset_x = float(scale_bar.offset_x)
    offset_y = float(scale_bar.offset_y)
    if scale_bar.location == "Upper Left":
        return offset_x, offset_y
    if scale_bar.location == "Upper Right":
        return image_width - bar_width - offset_x, offset_y
    if scale_bar.location == "Lower Left":
        return offset_x, image_height - bar_height - offset_y
    return image_width - bar_width - offset_x, image_height - bar_height - offset_y


def _display_compatible(image: np.ndarray) -> np.ndarray:
    array = np.asarray(image)
    if array.dtype == np.uint8:
        return array
    if np.issubdtype(array.dtype, np.integer):
        info = np.iinfo(array.dtype)
        return np.clip((array.astype(np.float32) / float(info.max)) * 255.0, 0, 255).astype(
            np.uint8
        )
    return np.clip(array * 255.0, 0, 255).astype(np.uint8)


def _rgba(value: str, opacity: float) -> tuple[int, int, int, int]:
    text = value.strip()
    alpha = max(0, min(255, int(round(255.0 * max(0.0, min(1.0, opacity))))))
    if text.startswith("#") and len(text) in {7, 9}:
        red = int(text[1:3], 16)
        green = int(text[3:5], 16)
        blue = int(text[5:7], 16)
        if len(text) == 9:
            alpha = int(text[7:9], 16)
        return red, green, blue, alpha
    return 255, 255, 255, alpha


def _font(size: float) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", max(1, int(round(size))))
    except OSError:
        return ImageFont.load_default()


def _asset_stem(asset: ImageAsset) -> str:
    return f"{_safe_name(Path(asset.filename).stem)}_{asset.id[:8]}"


def _safe_name(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value.strip())
    return safe.strip("_") or "item"
