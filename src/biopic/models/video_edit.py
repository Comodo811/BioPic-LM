"""Non-destructive video cut model for stack extraction."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VideoSegment:
    """One timeline segment in seconds."""

    start: float
    end: float
    retained: bool = True

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass(slots=True)
class VideoEditModel:
    """Retained/deleted time ranges for a source video."""

    duration: float = 0.0
    segments: list[VideoSegment] | None = None
    selected_index: int | None = None

    def __post_init__(self) -> None:
        if self.segments is None:
            self.segments = [VideoSegment(0.0, max(0.0, self.duration), True)]

    def retained_segments(self) -> list[VideoSegment]:
        return [
            segment
            for segment in self.segments or []
            if segment.retained and segment.duration > 0.0
        ]

    def effective_duration(self) -> float:
        return sum(segment.duration for segment in self.retained_segments())

    def segment_at_source_time(self, time_seconds: float) -> VideoSegment | None:
        time_seconds = max(0.0, min(float(time_seconds), self.duration))
        for segment in self.segments or []:
            if segment.start <= time_seconds <= segment.end:
                return segment
        return None

    def next_retained_time(self, time_seconds: float) -> float | None:
        time_seconds = max(0.0, min(float(time_seconds), self.duration))
        for segment in self.retained_segments():
            if time_seconds <= segment.end:
                return max(segment.start, time_seconds)
        retained = self.retained_segments()
        return retained[-1].start if retained else None

    def source_to_effective_time(self, time_seconds: float) -> float:
        time_seconds = max(0.0, min(float(time_seconds), self.duration))
        elapsed = 0.0
        for segment in self.segments or []:
            if not segment.retained:
                continue
            if time_seconds <= segment.start:
                return elapsed
            if time_seconds <= segment.end:
                return elapsed + (time_seconds - segment.start)
            elapsed += segment.duration
        return elapsed

    def effective_to_source_time(self, effective_seconds: float) -> float:
        effective_seconds = max(0.0, min(float(effective_seconds), self.effective_duration()))
        elapsed = 0.0
        retained = self.retained_segments()
        for segment in retained:
            next_elapsed = elapsed + segment.duration
            if effective_seconds <= next_elapsed:
                return segment.start + (effective_seconds - elapsed)
            elapsed = next_elapsed
        return retained[-1].end if retained else 0.0

    def split_at(self, time_seconds: float) -> bool:
        """Split the segment containing ``time_seconds``."""
        time_seconds = max(0.0, min(float(time_seconds), self.duration))
        for index, segment in enumerate(list(self.segments or [])):
            if segment.start + 1e-6 < time_seconds < segment.end - 1e-6:
                replacement = [
                    VideoSegment(segment.start, time_seconds, segment.retained),
                    VideoSegment(time_seconds, segment.end, segment.retained),
                ]
                assert self.segments is not None
                self.segments[index : index + 1] = replacement
                self.selected_index = index
                return True
        return False

    def delete_selected(self) -> bool:
        """Mark the selected segment deleted."""
        if self.segments is None or self.selected_index is None:
            return False
        if not (0 <= self.selected_index < len(self.segments)):
            return False
        segment = self.segments[self.selected_index]
        if not segment.retained:
            return False
        self.segments[self.selected_index] = VideoSegment(segment.start, segment.end, False)
        return True

    def select_at(self, time_seconds: float) -> int | None:
        """Select the segment containing ``time_seconds``."""
        time_seconds = max(0.0, min(float(time_seconds), self.duration))
        for index, segment in enumerate(self.segments or []):
            if segment.start <= time_seconds <= segment.end:
                self.selected_index = index
                return index
        self.selected_index = None
        return None

    def snapshot(self) -> tuple[list[VideoSegment], int | None]:
        return (list(self.segments or []), self.selected_index)

    def restore(self, snapshot: tuple[list[VideoSegment], int | None]) -> None:
        self.segments = list(snapshot[0])
        self.selected_index = snapshot[1]


def frame_timestamps(segments: list[VideoSegment], interval_seconds: float) -> list[float]:
    """Return deterministic extraction timestamps without boundary duplicates."""
    interval = float(interval_seconds)
    if interval <= 0:
        raise ValueError("interval_seconds must be greater than zero")
    timestamps: list[float] = []
    last = -1.0
    for segment in segments:
        if not segment.retained or segment.duration <= 0:
            continue
        count = int(segment.duration // interval) + 1
        for index in range(count):
            timestamp = min(segment.end, segment.start + index * interval)
            if timestamp <= last + 1e-6:
                continue
            timestamps.append(timestamp)
            last = timestamp
    return timestamps
