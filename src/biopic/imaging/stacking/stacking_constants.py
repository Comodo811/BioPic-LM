"""Constants recovered from the reference stacking path."""

from __future__ import annotations

BYTE_MAX = 255.0
BYTE_MAX_INT = 255
BYTE_ROUND_INT = 0x7F

MINIMUM_SCORE_MAX = 29
MINIMUM_SCORE_TO_BYTE = 3.0
PATCH_ADJUST_MIN = -10
PATCH_ADJUST_MAX = 10
FILTER_SET_MIN = 1
FILTER_SET_MAX = 5
FIXED_FILTER_MIN = 1
FIXED_FILTER_MAX = 10

RGB_TO_GRAY_R = 0x36 / BYTE_MAX
RGB_TO_GRAY_G = 0x78 / BYTE_MAX
RGB_TO_GRAY_B = 0x51 / BYTE_MAX

DETAIL_SMOOTH_DENOMINATOR = 28.0
DETAIL_SCORE_SATURATION_OFFSET = 0x80
DETAIL_SCORE_NUMERATOR_SCALE = 256.0

INCREMENTAL_REPLACE_DELTA = 1.0 / BYTE_MAX
INCREMENTAL_OLD_WEIGHT_COEFFICIENTS = (0x33 / BYTE_MAX, 0x40 / BYTE_MAX, 0x55 / BYTE_MAX)
SUPPORT_SCORE_HIGH_WEIGHT = 2.0
SUPPORT_SCORE_MID_WEIGHT = 1.0
SUPPORT_SCORE_DENOMINATOR = 3.0

LOW_SCORE_CURRENT_NUMERATOR = 127.0
LOW_SCORE_DETAIL_FRACTION = 0.5
LOW_SCORE_CONFIDENCE_SMOOTH_DENOMINATOR = 24.0

FINAL_COMPOSITE_CURRENT_NUMERATOR = 2.0
SUPPRESSION_PERCENT_DENOMINATOR = 100.0

SPARSE_WIDE_SMOOTH_DIVISOR = 3736.0

# Optional alignment helper constants.
ALIGNMENT_HALF_SCALE_DENOMINATOR = 2.0
ALIGNMENT_BASE_SCALE = 1.0
ALIGNMENT_DEGREES_TO_RADIANS = 0.017453292519943295
ALIGNMENT_FINE_STEP = 0.1
ALIGNMENT_DECAY = 0.9
ALIGNMENT_SEARCH_DECAY = 0.9
ALIGNMENT_SEARCH_ONE = 1.0
ALIGNMENT_SEARCH_COARSE = 0.6
ALIGNMENT_SEARCH_LIMIT = 1.2
ALIGNMENT_SEARCH_FINE = 0.67

# Resolved from the reference stacking parameter table
# The reference formula is: channel_scale = channel * slope + intercept.
DETAIL_CHANNEL_GAIN_SLOPE = 0.04
DETAIL_CHANNEL_GAIN_INTERCEPT = 0.5
DETAIL_CHANNEL_GAINS = (
    DETAIL_CHANNEL_GAIN_INTERCEPT,
    DETAIL_CHANNEL_GAIN_INTERCEPT + DETAIL_CHANNEL_GAIN_SLOPE,
    DETAIL_CHANNEL_GAIN_INTERCEPT + 2.0 * DETAIL_CHANNEL_GAIN_SLOPE,
)

# Resolved from the reference stacking parameter table.
FRAME_SCALE_DENOMINATOR = 255.0
HIGH_LOW_PREFERENCE_BASE = -0.03
HIGH_LOW_PREFERENCE_SLOPE = 0.02
FRAME_GAIN_BASE = 1.0
DEFAULT_FRAME_GAIN_SLOPE = -0.03

# Deprecated: this fitted response was used before the Custom stack used
# rendered RAW input. The stacker no longer applies it.
OUTPUT_COLOR_MATRIX = (
    (0.3504395, -0.04618032, -0.42086795),
    (0.35692722, 0.5785615, 0.03260363),
    (-0.00501144, 0.3900824, 1.160753),
)
OUTPUT_COLOR_BIAS = (0.10852867, 0.01419322, 0.10363169)
# Deprecated constants from an empirical output-detail experiment.
# The reference Custom stack path does not contain a standalone RGB high-pass
# after final compositing.
OUTPUT_DETAIL_SIGMA = 0.65
OUTPUT_DETAIL_AMOUNT = 0.35

# Resolved from the reference stacking parameter table.
# The smart-filter formula operates on byte-scale confidence values.
SMART_HIGH_CONFIDENCE_WEIGHT = 1.33
SMART_DENOMINATOR_BIAS = 1.0
SMART_MID_CONFIDENCE_WEIGHT = 1.2
SMART_LOW_CONFIDENCE_WEIGHT = 1.0
SMART_HIGH_BYTE_WEIGHT_SCALE = 339.15000000000003
SMART_MID_BYTE_WEIGHT_SCALE = 306.0
SMART_BLEND_DENOMINATOR = 255.0


def minimum_score_threshold_unit(score_threshold: int) -> float:
    """Return the reference byte threshold as a normalized unit value."""

    level = max(0, min(MINIMUM_SCORE_MAX, int(score_threshold)))
    return min(1.0, (level * MINIMUM_SCORE_TO_BYTE) / BYTE_MAX)


def minimum_score_threshold_byte(score_threshold: int) -> int:
    """Return the reference byte threshold."""

    level = max(0, min(MINIMUM_SCORE_MAX, int(score_threshold)))
    return int(level * MINIMUM_SCORE_TO_BYTE)


def detail_channel_gain(channel_index: int) -> float:
    """Return the resolved gain for one detail score channel."""

    index = max(0, min(2, int(channel_index)))
    return float(DETAIL_CHANNEL_GAINS[index])


def default_frame_filter_slope() -> float:
    """Return the default high/low frame preference slope."""

    return DEFAULT_FRAME_GAIN_SLOPE


def frame_index_byte(frame_index: int, frame_count: int) -> int:
    """Map the reference reverse-loop frame index to its 0..255 byte position."""

    count = max(1, int(frame_count))
    return int(round(int(frame_index) * (FRAME_SCALE_DENOMINATOR / count)))


def frame_score_gain(frame_index: int, frame_count: int, filter_slope: float | None = None) -> float:
    """Return the per-frame score gain used before focus scoring."""

    slope = default_frame_filter_slope() if filter_slope is None else float(filter_slope)
    index_byte = frame_index_byte(frame_index, frame_count)
    return float(
        FRAME_GAIN_BASE
        - (slope * (index_byte - 0x7F)) / FRAME_SCALE_DENOMINATOR
    )
