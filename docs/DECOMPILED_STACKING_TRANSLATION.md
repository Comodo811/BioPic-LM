# Decompiled Stacking Translation Notes

Source: `decomp.txt`

Fast references:

- Raw extracted decompiler output: `docs/decompiled_stacking_core_functions.c`
- Raw extracted adjacent helpers: `docs/decompiled_stacking_additional_functions.c`
- Clean translated reference: `docs/decompiled_stacking_clean_reference.py`

These notes translate the clearest stacking functions into BioPic implementation targets. The source is decompiled Ghidra output, so variable names are inferred.

## `FUN_008c1ac0` - Incremental Multi-Buffer Update

- Reads minimum score from UI control `0x808`.
- Converts it to an 8-bit threshold by `threshold = minimum_score * 3`.
- Reads three score channels from the current processed frame.
- Maintains three image buffers:
  - `DAT_00968f80`
  - `DAT_00968f88`
  - `DAT_00968f90`
- Maintains three matching confidence/id buffers:
  - `DAT_00968f38`
  - `DAT_00968f40`
  - `DAT_00968f48`
- For each channel, if the new score is greater than the existing confidence plus one, it blends old and new source pixels with fixed-point weights:
  - channel 0: `old_weight = old_confidence * 0x33 / new_score`
  - channel 1: `old_weight = old_confidence * 0x40 / new_score`
  - channel 2: `old_weight = old_confidence * 0x55 / new_score`
  - `new_weight = 0xff - old_weight`
  - output pixel = `(old * old_weight + new * new_weight + 0x7f) / 0xff`
- It also builds `DAT_00968ee8` when `(score0 * 2 + score1) / constant` exceeds `minimum_score * 3`.

## `FUN_008c1050` - Combine Detail Buffers

- Copies `DAT_00968f88` into both `DAT_00968f98` and `DAT_00968fa0`.
- If Smart filter is off, fixed filter value `1..10` maps to three weights.
- Exact fixed mapping:
  - `1`: high-detail buffer only: `(255, 0, 0)`
  - `2..5`: `w0 = filter * -0x40 + 0x140`, `w1 = 255 - w0`, `w2 = 0`
  - `6..9`: `w0 = (filter - 5) * -0x1e + 0x78`, `w2 = (filter - 5) * 0x32`, `w1 = 255 - (w0 + w2)`
  - `10`: low-detail buffer only: `(0, 0, 255)`
- If Smart filter is on, weights are computed from the three confidence buffers.
- Both RGB output and confidence/id map are combined using the same weights.

## `FUN_0085f120` And Helpers - Detail Buffer Construction

- `FUN_0085f120` creates three score/detail channels before `FUN_008c1ac0` updates the running buffers.
- `FUN_008644a0` converts RGB to grayscale before scoring:
  - gray = `(R * 0x36 + G * 0x78 + B * 0x51 + 0x7f) / 0xff`
- `FUN_0085ec00` contains a clear smoothing/detail split:
  - smooth value = `(cardinal_neighbors * 4 + diagonal_neighbors * 3) / 28`
  - the center pixel is intentionally excluded from this smoothing stencil.
  - detail value = `abs(center - smooth)`.
- `FUN_0085ee70` converts local detail into one of three score channels:
  - local support uses `center * 4 + cardinal * 3 + diagonal * 2`.
  - score is saturated through `(value << 8) / (value + 0x80)`.
  - exact global scale constants are still unresolved.
- `FUN_0085dec0` downscales by averaging 2x2 or 3x3 blocks.
- `FUN_0085e2a0` upsamples score channels with bilinear interpolation.
- `FUN_0085e4d0` applies a wide channel-dependent smoothing/cleanup kernel after score upsampling.
- `FUN_0085ffb0` tracks dark, bright and accumulated buffers:
  - on first frame it copies the source into min, max and accumulator buffers.
  - on later frames it keeps per-pixel minimum and maximum and adds scaled source values to a 16-bit accumulator.
- BioPic Custom now uses these decompiled-style background choices:
  - `darkest`: per-pixel darkest luminance source
  - `brightest`: per-pixel brightest luminance source
  - `mixed`: average of darkest and brightest buffers
  - `first` / `last`: direct source frame

BioPic translation status:

- The fixed filter weight table is exact.
- The neighbor smoothing stencil is exact.
- The RGB-to-gray weights are exact.
- The Custom stacker now maintains three running source buffers, three confidence buffers and three depth/id buffers frame by frame.
- Custom no longer applies BioPic's extra post-stack detail enhancement pass after final decompiled-style compositing.
- The score support and saturating curve are translated, but the global contrast constants from `param_1 + 0xa0`, `_DAT_0085f110` and `_DAT_0085f118` are still approximated.
- The wide `FUN_0085e4d0` score cleanup kernel is translated with its sparse weights and divisor `3736`.
- The decompiled score path uses byte buffers throughout `FUN_0085ec00`, `FUN_0085ee70`, `FUN_0085e2a0`, and `FUN_0085e4d0`. BioPic now quantizes the Custom score path to 8-bit precision at the same stages. Without this, sub-byte float ripples from the sparse cleanup kernel survive and become visible confidence/depth-selection waves.
- `FUN_0085e4d0` horizontal offsets are byte offsets into a 3-channel interleaved score map, not pixel offsets. BioPic previously treated them as pixel offsets, making the sparse cleanup about 3x too wide horizontally and introducing visible wavy selection patterns.

## `FUN_008c37b0` - Ring-Supported Confidence Cleanup

- Copies the confidence/id map before editing.
- For each interior pixel, checks sparse ring points around the current pixel.
- The threshold is stored at `param_1 + 0x6b`, normally `minimum_score * 3`.
- It first checks 8 neighbors at radius pattern `2`.
- If fewer than three strong neighbors are found, it checks another 8 at radius pattern `3`.
- If still fewer than three, it checks another 8 at radius pattern `6`.
- If still fewer than three, it checks another 8 at radius pattern `9`.
- If at least two strong neighbors are found:
  - confidence channel becomes `threshold + 1`
  - id/depth channel becomes average of neighbor ids
- This explains the clean background: isolated background noise has no supporting ring neighbors, so it remains below threshold and is later blended to background.

## `FUN_008c3240` - Patch Narrow/Widen

- Reads `minimum_score * 3`.
- Reads patch adjustment from control `0xa48`.
- Negative adjustment:
  - if center score is strong and any circular-neighborhood score is weak, set center score to `threshold - 1` and id to `0x7f`.
- Positive adjustment:
  - if center score is weak and circular-neighborhood strong pixels exist, set center score to `threshold + 1` and id to weighted average neighbor id.

## `FUN_008c4770` - Low-Score Transition Pass

- For pixels below `minimum_score * 3`, blends current result with detail/background buffers.
- Uses:
  - `a = score * 127 / threshold`
  - `b = a / 2`
  - `c = 255 - (a + b)`
  - output = `(current * a + detail * b + background * c) / 255`
- Smooths the confidence/id map with a 3x3 weighted stencil.
- BioPic now applies this before the final `FUN_008c4290` background composite. It smooths the confidence map with the exact 3x3 weights; the decompiled id-map smoothing is approximated because BioPic stores depth separately from the RGB confidence/id buffer.

BioPic ordering note:

- Custom now follows the decompiled order more closely:
  1. combine detail buffers with `FUN_008c1050` logic;
  2. apply low-score transition `FUN_008c4770`;
  3. apply patch adjust `FUN_008c3240`;
  4. apply ring-supported cleanup inside the final-composite stage like `FUN_008c4290`.
- The decompiled frame list is walked from the end internally, but BioPic keeps the user-provided stack order because reversing the already-loaded BioPic list biased the running buffers toward the last image.
- BioPic uses the hard best-focus depth/source layer for specimen detail and depth output, while keeping the decompiled multi-buffer confidence/background logic for flat regions. This avoids fixed-filter depth rounding making the result look like mostly the last frame.
- Important implementation detail from the raw `FUN_008c1ac0` loop: source, confidence and depth buffers are written only for pixels where `new_score > old_score + 1`. A vectorized full-array update will overwrite earlier sharp pixels with later blurred frames and causes the organism-edge blur seen in BioPic before this fix.
- Ring-supported cleanup is gated by local confidence evidence in BioPic so distant sparse-ring support cannot promote completely flat background pixels into visible wavy bands.

## `FUN_008c4290` - Final Composite

- Reads `minimum_score * 3`.
- If threshold is greater than `5`, calls `FUN_008c37b0`.
- If the program noise suppression global is nonzero, calls `FUN_008c3650`.
- If confidence is above threshold, the depth-map display gets a palette color.
- Otherwise final RGB blends current result with background:
  - `current_weight = confidence * 0x1fe / (threshold + confidence)`
  - `background_weight = 0xff - current_weight`
  - output = `(current * current_weight + background * background_weight) / 255`
- If noise suppression is nonzero, final output is blended again with `DAT_00968ee8`:
  - `output = (output * (100 - suppression) + DAT_00968ee8 * suppression) / 100`

## BioPic Translation Targets

- Use the fixed filter weight table exactly for Custom with Adaptive off.
- Add the ring-supported confidence cleanup from `FUN_008c37b0`.
- Make the final Custom background composite use the exact confidence formula from `FUN_008c4290`.
- Keep patch adjust as a separate confidence/id-map edit rather than generic depth morphology.
- Next unresolved items:
  - resolve the exact constants used by `FUN_0085ee70`;
  - translate the id-map part of `FUN_008c4770` more exactly if the depth-map export needs to match the decompiled program pixel-for-pixel.

## Additional Decompiled Code Reviewed

These functions were found after scanning the wider stacking/global range. They are in `docs/decompiled_stacking_additional_functions.c`.

### Useful For Focus-Stacking Behavior

- `FUN_008c2820` - main per-frame stack loop:
  - iterates frames in reverse order;
  - initializes the three detail buffers and confidence/id buffers from the first processed frame;
  - optionally aligns each following frame with `FUN_00865340`;
  - updates dark/bright/accumulated background buffers with `FUN_0085ffb0`;
  - updates running detail buffers with `FUN_0085f120` and `FUN_008c1ac0`;
  - previews `DAT_00968f88` or `DAT_00968ee8`, not the final composite;
  - uses `DAT_00969010` as a preview/processing skip counter.
- `FUN_00865340` - optional alignment correction:
  - converts both frames to decompiled grayscale;
  - downsamples when the frame has at least `0x7e9000` pixels;
  - estimates correction with `FUN_00864bb0`;
  - can apply shift, scale and rotation-like correction helpers;
  - smooths the next starting offset from the previous offset.
- `FUN_00864bb0` / `FUN_00864660` - alignment search:
  - iterative coordinate descent over shift, and optionally scale/rotation;
  - uses sparse sample scoring instead of dense full-image correlation;
  - stops after repeated no-improvement steps.
- `FUN_0085ffb0`, `FUN_0085fe50`, `FUN_0085fcc0` - background/average buffers:
  - maintains darkest, brightest and accumulated-average buffers;
  - accumulated average uses 16-bit storage and a frame-count scaling byte.
- `FUN_008c0fc0` - auto-enhance setup:
  - sets bit flags for two auto-enhance options and clears tracking values.

### Useful Mostly For UI/Performance Semantics

- `FUN_008cffc0`, `FUN_008d0060`, `FUN_008d0100`, `FUN_008d01a0`, `FUN_008d0240`:
  - set `DAT_00969010` to `0`, `1`, `2`, `4`, or `9`;
  - label this as "Stack 1 image / Skip ...";
  - this looks like a speed/preview skipping option, not part of final quality unless frames are actually skipped.
- `FUN_008c24b0`:
  - saves intermediate `step_###.bmp` files;
  - uses `DAT_00968f88` for normal stacking progress and `DAT_00968ee8` when suppression is high;
  - output-only, not needed for stack quality.
- `FUN_008c2750`:
  - validates matching dimensions;
  - BioPic already validates stack shapes.
- `FUN_008c08c0`:
  - initializes stack buffers from the first source frame and updates display state;
  - useful as confirmation, but already covered by the Custom buffer initialization.

### Depth Map / Output Helpers

- `FUN_0085f730`:
  - inverts the id/depth byte channel;
  - applies palette colors when RGB channel difference is high;
  - only relevant if BioPic wants a decompiled-style colored depth-map export.
- `FUN_0085f8c0`:
  - writes a grayscale depth map by copying the inverted id/depth channel into all RGB channels;
  - useful for matching decompiled depth-map file output.
- `FUN_008c9cb0`:
  - concatenates two images horizontally and saves them;
  - output utility, not focus stacking.

### Related But Not Focus-Stacking Core

- `FUN_008c6d20`:
  - plain averaging over frames using the same dark/bright/average buffer helpers.
- `FUN_008c6f90`:
  - background correction mode, not the focus-stack synthesis method.
- `FUN_008c83d0`:
  - colour stacking mode;
  - uses channel ordering and local channel contrast, not the focus method.
- `FUN_008c9520`, `FUN_008c9cb0`, `FUN_008cc6a0`:
  - workflow/display/export helpers.

## New Translation Opportunities

1. Add an optional decompiled-style fast alignment mode:
   - grayscale only;
   - downsample large frames;
   - sparse coordinate-descent shift search;
   - optional rotation/scale only when enabled.
2. Add decompiled-style depth-map export:
   - grayscale id map from `FUN_0085f8c0`;
   - optional palette overlay from `FUN_0085f730`.
3. Add a "Skip frames during stacking" speed option only if the UI should mimic the decompiled program's `DAT_00969010` behavior.
4. Keep background correction, colour stacking and averaging as separate future tools, not as part of Custom focus stacking.
