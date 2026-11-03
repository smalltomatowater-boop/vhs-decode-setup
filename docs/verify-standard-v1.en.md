*[日本語](verify-standard-v1.md) · **English***

# Verification record: profile-standard-v1

- Date: 2026-11-02
- Material: tape01 (VHS / NTSC / 28m27s / a visual-kei music video compilation)
- Preservation master: `master_tape01.mkv` (FFV1 yuv422p10le, full range, 19GB)
- Deliverable: `tape01_standard.mp4` (H.264 CRF18, 784MB)

## Scope of this record (important)

**These are measurements from three representative scenes, not a quality
guarantee for the whole tape.** Another tape, or another scene, can give
different results. Run the same verification on the next tape and confirm the
settings do not break down when the source material changes.

Scenes verified:

| Scene | Time | Why it was chosen |
|---|---|---|
| Black silhouette on snow | 651.5s | A dark figure against a bright background; prone to crushed blacks |
| Black suit against a white wall | 653.5s | Shadow detail and blown highlights in the same frame — the hardest case |
| Dim interior | 630.0s | Dark throughout, with compressed tonality |

## Separating the stages

Four stages were compared under identical conditions (640x480 / 8-bit /
limited-range encoding).

| Stage | Contents |
|---|---|
| A | Unprocessed (deinterlace, crop and full→limited conversion only) |
| B | A + black point 68 |
| C | B + hqdn3d (the final state before encoding) |
| D | The final MP4 |

## Results

### Structural loss (as a fraction of the whole frame)

| Scene | A | B | C | D |
|---|---|---|---|---|
| Black silhouette on snow | 0.0000% | 0.0157% | 0.0092% | 0.0279% |
| Black suit, white wall | 0.0000% | 0.0388% | 0.0448% | **0.0668%** |
| Dim interior | 0.0000% | 0.0000% | 0.0000% | 0.0000% |

"Structure" = crushed pixels (Y ≤ 16) that form a horizontal run of 10 or more.
Isolated one- or two-pixel hits are noise troughs, not structure.

### Blown highlights

0.001–0.020% across every stage and scene. Tonality in the white wall (its
corner, the step, the floor, the vignetting) was confirmed to survive in all
four stages under a highlight-stretched view.

### Noise

The black-point correction amplifies noise by `1023/(1023-68)` = **1.0712×**
(a mathematical consequence). hqdn3d offsets this, leaving a final figure of
**-2.3% to +7.8%** relative to unprocessed.

### Encoding fidelity (C→D)

| Scene | SSIM | PSNR |
|---|---|---|
| Black silhouette on snow | 0.9694 | 40.94 dB |
| Black suit, white wall | 0.9743 | 43.49 dB |
| Dim interior | 0.9613 | 41.48 dB |

Laplacian response (fine detail) drops substantially from C to D, but given
SSIM and PSNR at the levels above, this was judged to be a reduction in noise
rather than a loss of structure.

### Audio

Waveform correlation against the master 0.9961–0.9977, offset ±32ms, no drift.
32ms is the measurement granularity (AAC encoder delay) and is inside the
perceptual threshold.

### Playback compatibility

H.264 High@L3.1 / yuv420p / AAC-LC 48kHz stereo / faststart (moov first).
Zero errors decoding the whole file.

## Limits of these metrics

- **Shadow and highlight tone counts saturated and were unusable.** A, B and C
  all occupied every level in the measurement band (63/63 and 53/53), so the
  stages cannot be compared. Only D dropped, to 54/45, which is the effect of
  8-bit quantisation.
- **Temporal noise includes subject motion.** The figure above 17 in the black
  silhouette scene is mostly motion, not noise.

## Known issue (not addressed in v1)

ffmpeg automatically adds a `tmcd` (QuickTime timecode) track. Major players
ignore it and no actual harm has been observed, but a deliverable does not need
a timecode. It can be suppressed with `-write_tmcd 0`. **The v1 verification
was carried out without that flag, so it stays out of v1 and will be evaluated
separately as standard-v2.**

To fix an existing file, do not re-encode: stream-copy video and audio into a
new container and re-check with `bin/vhsverify`.
