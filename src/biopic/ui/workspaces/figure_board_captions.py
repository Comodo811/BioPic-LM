"""Caption generation and editing for figure boards."""

from __future__ import annotations

from biopic.imaging.project_render import asset_for_source_node
from biopic.models.annotations import AnnotationDefinition, AnnotationKind
from biopic.models.figure_board import FigureBoard, common_scale_bar_value_key, visual_panel_order
from biopic.ui.workspace_helpers.common import biological_display_name as _biological_display_name


class FigureBoardCaptionsMixin:
    def _update_caption(self, board: FigureBoard) -> None:
        parts = ["Figure."]
        caption_scale_bars = []
        for panel in visual_panel_order(board.panels):
            if panel.source_node_id is None:
                parts.append(f"{panel.label}. Empty panel.")
                continue
            asset = asset_for_source_node(self.project, panel.source_node_id)
            metadata = asset.metadata if asset is not None else {}
            scientific_name = metadata.get("scientific_name") or metadata.get("Scientific name")
            taxonomy = metadata.get("taxonomy")
            orientation = metadata.get("orientation") or metadata.get("Orientation")
            body_part = metadata.get("body_part")
            side = metadata.get("side")
            sex = metadata.get("sex")
            life_stage = metadata.get("life_stage")
            locality = metadata.get("locality")
            magnification = metadata.get("magnification")
            preparation = metadata.get("preparation")
            description = _biological_display_name(
                scientific_name,
                taxonomy,
                asset.filename if asset is not None else "Image",
            )
            if orientation:
                description = f"{description}, {orientation} view"
            if body_part:
                description = f"{description}, {body_part}"
            if side and side != "not applicable":
                description = f"{description}, {side} side"
            if sex:
                description = f"{description}, {sex}"
            if life_stage:
                description = f"{description}, {life_stage}"
            if magnification:
                description = f"{description}, {magnification}"
            if preparation:
                description = f"{description}, {preparation}"
            if locality:
                description = f"{description}, collected at {locality}"
            parts.append(f"{panel.label}. {description}.")
            for scale_bar in self.project.scale_bars.values():
                if scale_bar.image_node_id == panel.source_node_id:
                    caption_scale_bars.append(scale_bar)
        common_scale = (
            common_scale_bar_value_key(caption_scale_bars)
            if board.hide_common_scale_bar_value
            else None
        )
        if common_scale is not None:
            physical_length, unit = common_scale
            parts.append(f"Scale bars: {physical_length:g} {unit}.")
        abbreviation_entries = self._board_abbreviation_legend_entries(board)
        if abbreviation_entries:
            parts.append(f"Abbreviations: {'; '.join(abbreviation_entries)}.")
        board.caption.update_auto_generated("\n".join(parts))

    def _board_abbreviation_legend_entries(self, board: FigureBoard) -> list[str]:
        source_ids = {
            panel.source_node_id
            for panel in board.panels
            if panel.source_node_id is not None
        }
        if not source_ids:
            return []
        definitions_by_id = self.project.annotation_definitions
        definitions_by_abbreviation = {
            definition.abbreviation.casefold(): definition
            for definition in definitions_by_id.values()
            if definition.include_in_legend
        }
        used: dict[str, AnnotationDefinition] = {}
        for annotation in self.project.annotations.values():
            if (
                annotation.image_node_id not in source_ids
                or not annotation.visible
                or not annotation.include_in_legend
                or annotation.kind is not AnnotationKind.TEXT
            ):
                continue
            definition = None
            if annotation.definition_id is not None:
                definition = definitions_by_id.get(annotation.definition_id)
            if definition is None and annotation.text:
                definition = definitions_by_abbreviation.get(annotation.text.casefold())
            if (
                definition is None
                or not definition.include_in_legend
                or not definition.abbreviation.strip()
                or not definition.full_definition.strip()
            ):
                continue
            used.setdefault(definition.abbreviation.casefold(), definition)
        return [
            f"{definition.abbreviation} = {definition.full_definition}"
            for definition in sorted(used.values(), key=lambda item: item.abbreviation.casefold())
        ]

    def _show_caption(self, board: FigureBoard) -> None:
        self.caption.blockSignals(True)
        self.caption.setPlainText(board.caption.visible_text())
        self.lock_caption.setChecked(board.caption.locked)
        self.caption.blockSignals(False)

    def _caption_edited(self) -> None:
        board = self._current_board()
        if board is None:
            return
        board.caption.user_text = self.caption.toPlainText()
        board.caption.user_modified = board.caption.user_text != board.caption.auto_generated
        self.project.touch()

    def _caption_lock_toggled(self, locked: bool) -> None:
        board = self._current_board()
        if board is None:
            return
        board.caption.locked = locked
        if locked:
            board.caption.user_modified = True
            board.caption.user_text = self.caption.toPlainText()
        self.project.touch()


