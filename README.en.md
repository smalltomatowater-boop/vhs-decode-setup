*[日本語](README.md) · **English***

# vhs-decode-setup

Build notes and automation for capturing VHS tapes **directly from the RF
signal** and decoding them in software.

A 2011-era second-hand PC running Ubuntu 24.04, a CX card tapping the raw FM
signal off the deck, and `vhs-decode` taking it all the way to colour video.

---

## What is specific to this repository

The decoding itself is upstream work
([cxadc](https://github.com/happycube/cxadc-linux3) /
[vhs-decode](https://github.com/oyvindln/vhs-decode) /
[tbc-tools](https://github.com/harrypm/tbc-tools)).
Only two things here are not available elsewhere.

### 1. Capture that completes from a single press of Play

```sh
vhstool watch tape01
```

It polls the RF level once a second, **starts recording when a signal
appears**, **stops when the tape ends**, then runs decode, colourisation,
audio merge and NAS transfer on its own. The only human action is pressing
Play.

A conventional capture (video + audio) runs in parallel, and the **two video
streams are cross-correlated to align the audio**.

### 2. Patches that make GV-USB2 work on current kernels

The I-O DATA GV-USB2 (a very common analogue capture device in Japan) neither
builds nor runs on current kernels.

| Symptom | Cause |
|---|---|
| `'const struct vb2_ops' has no member named 'wait_prepare'` | Linux 6.10 removed those vb2 callbacks |
| `urb submit failed (-11)` / `swiotlb buffer is full (sz: 786432 bytes)` | **Not a USB bandwidth problem.** A DMA request larger than swiotlb's 256KB per-mapping limit |

The second one only happens with **EHCI (USB 2.0 era) × more than 4GB of RAM ×
no IOMMU** — exactly the combination you walk into when you buy an old PC for
VHS digitisation.

→ [`patches/`](patches/) · the upstream report is in
[`docs/upstream-report-gvusb2.md`](docs/upstream-report-gvusb2.md)

---

## The rig

| | |
|---|---|
| PC | Dell Vostro 460 / Core i7-2600 (4C8T) / 16GB / Ubuntu 24.04.4 LTS |
| Kernel | 7.0.0-42-generic |
| RF capture | Conexant CX23880 (PCI) + [cxadc](https://github.com/happycube/cxadc-linux3) |
| Reference capture | I-O DATA GV-USB2 (USB) + [GV-USB2-Driver](https://github.com/Isaac-Lozano/GV-USB2-Driver) |
| Deck | JVC HR-VX100 |
| Capture target | Internal SATA SSD, 238GB, dedicated ext4 (measured 397MB/s) |
| Finishing machine | Apple M4 10-core / 32GB / macOS 26.5.1 (everything from export onwards) |
| Storage | NAS 3.6TB (SMB, 1000baseT), split into three shares |

### Signal path

```
          ┌─ TP106 (PB FM) ──→ CX23880 ──→ cxadc ──→ vhs-decode ──→ video
VHS deck ─┤
          └─ AV out ─────────→ GV-USB2 ──→ v4l2/ALSA ──→ audio + sync reference
                                                            │
                                              merge ────────┘
```

Video comes over RF; audio comes from the ordinary AV output. The **video** of
the reference capture is not thrown away — it is the **reference used to align
the two streams**.

### What is in this repository

```
setup.sh           Builds the Ubuntu machine (capture and decode)
setup-mac.sh       Builds and verifies the Mac (export onwards)
bin/
  vhstool          [Ubuntu] Capture through decode, audio merge, NAS transfer
  vhslevel.py      [Ubuntu] Inspect the RF signal level
  vhsfinish        [Mac] Nine stages from export to deliverables (resumable)
  vhsclean         [Mac] Clear out intermediates after finishing
  vhsdeliver       Produce delivery MP4s from a preservation master (profile-driven)
  vhsverify        15 automated checks on a deliverable
  vhsalign.py      Measure RF-vs-reference offset (multiple windows)
  vhsqa.py         Measure what is lost at each stage
profiles/
  standard-v1.sh   Frozen values for the standard delivery (black point 68)
  contrast-v1.sh   Contrast-oriented variant (black point 84)
config/            cxadc and GV-USB2 configuration
patches/           Three fixes not yet upstream
docs/
  flow.md          The whole pipeline, ready to copy and paste
  verify-*.md/csv  Verification records
  upstream-*.md    Draft reports for upstream
```

The work is split across two machines. Capture and decode run on the Ubuntu
box; **everything from export onwards runs on the Mac**, because of the Ubuntu
box's faulty RAM (pitfall 9 below). The full pipeline is written out in
[docs/flow.en.md](docs/flow.en.md).

---

## Pitfalls (the important part)

If you are reproducing this setup, this section is the one worth reading.

### 1. cxadc parameters cannot be set from modprobe.d

`vmux` / `level` / `sixdb` are **custom sysfs attributes, not module
parameters**. `modinfo cxadc` shows no `parm:` entries at all.

```sh
# ✗ has no effect
options cxadc vmux=2 level=24 sixdb=1

# ✓ set them through udev ATTR
KERNEL=="cxadc0", SUBSYSTEM=="cxadc", ATTR{device/parameters/vmux}="2", ...
```

→ [`config/cxadc.rules`](config/cxadc.rules)

### 2. vhs-decode needs Rust 1.78 or newer

`Cargo.lock` is lockfile v4. With Ubuntu 24.04's `cargo` 1.75 you get

```
error: lock file version 4 requires `-Znext-lockfile-bump`
```

Look at the **lockfile version**, not the `edition`. Install stable via
`rustup`.

### 3. ld-chroma-decoder has moved and been renamed

It exists in **neither** `vhs-decode` nor `happycube/ld-decode` (the official
wiki is out of date).

```
ld-chroma-decoder  →  tbc-chroma-decoder
at: https://github.com/harrypm/tbc-tools
```

### 4. tbc-tools needs the Linux ONNX Runtime SDK

The repository's `external/onnxruntime/` contains **only the Windows build**,
and there is no option to disable it (`FATAL_ERROR`). Download Microsoft's
official Linux build and point CMake at it.

### 5. tbc-tools requires flac 1.5.0; Ubuntu 24.04 ships 1.4.3

Only `src/ld-lds-converter` (LaserDisc-specific) requires it, and no other
tool depends on that. Drop it from the build.

→ [`patches/tbc-tools-01-skip-ld-lds-converter.patch`](patches/)

### 6. The GV-USB2 driver neither builds nor runs on current kernels

**(a) Removed vb2 callbacks** (Linux 6.10 and later)

```
error: 'const struct vb2_ops' has no member named 'wait_prepare'
```

The driver already sets `vb2q->lock`, so vb2 locks on its own. Deleting two
lines is the whole fix.

**(b) Exceeding swiotlb's per-mapping limit** — this is the nasty one

```
ehci-pci: swiotlb buffer is full (sz: 786432 bytes)
gvusb2-vid: urb submit failed (-11)
```

This is **not** a USB bandwidth problem; there was bandwidth to spare.

- EHCI can only do 32-bit DMA
- This machine has 16GB, so anything above 4GB goes through swiotlb bounce buffers
- swiotlb's per-mapping limit is **256KB**
- The driver asked for `0x100 packets × 0xc00 bytes = 786432 bytes` — **3× over**

The H67 chipset has no VT-d (IOMMU), so there is no way around it. Quarter the
packets per URB and double the URB count.

**A landmine you only hit on a USB 2.0-era PC with more than 4GB of RAM.**

→ [`patches/gvusb2-02-swiotlb-urb-size.patch`](patches/)

### 7. tbc-video-export writes full-range content but tags it `tv`

The content is **black = 0 / white = 1023** (full range), but the file says
`color_range=tv` (black = 64 / white = 940). Leave that mismatch in place and
players crush everything above 940 to pure white. On the material measured
here, **20% of the picture sat above 940**.

```sh
# Measured mapping (16-bit TBC → 10-bit output)
#   16-bit 16219 (=black16bIre) → 10-bit 0
#   16-bit 56577 (≈white16bIre) → 10-bit 1023
# Limited range would be slope 0.02186, full range 0.02553. Measured: 0.0251–0.0253.

# The fix (not a single byte of content is rewritten; 0.2s even for 19GB)
mkvpropedit master_tape01.mkv --edit track:v1 --set colour-range=2
```

`bin/vhsdeliver` checks the master's `color_range` before producing a
deliverable and refuses to run unless it is `pc`, so a double conversion
cannot happen by accident.

**A consequence of this design is that export clips at 100 IRE.** The TBC holds
up to +122.5 IRE, but the output is cut at roughly +100.6 IRE, and measurement
showed **2.5%** of pixels being lost. 78% of those were a few-pixel overshoot
(edge ringing) and only 22% genuine bright area. Raising `white16bIre` in the
JSON would give headroom (no re-decode needed), but that is untested.

### 8. An old `tbc-video-export` in `~/.local/bin` shadows your new build

If the pip-installed 0.1.8 comes first on `PATH`, it hides the 3.3.0 you just
built. 0.1.8 looks for the helper under its old name `ld-dropout-correct` and
therefore always fails.

```
FileIOError: ld-dropout-correct not in PATH or script dir.
```

This hit immediately after a five-hour decode. `vhstool` now orders `PATH` as
`"$BIN:$HOME/.local/bin:$PATH"`.

---

### 9. Faulty non-ECC RAM disguises itself as a decoding failure

CRC mismatches went from 18 to 2 and would not reproduce. Half a day went into
suspecting a decoder bug.

Three observations settled it:

```
Read the same file three times   → the mismatch positions move every time
                                    (the read path is corrupting it)
Decode the same RF on the Mac    → 0 mismatches
Compare dropout-correction counts → both machines: exactly 18338
```

The third was decisive. If the correction counts agree, **the decode itself is
sound** and only the path behind it can be broken. SATA transfer errors were 0
and uncorrectable SSD errors were 0, which leaves memory: 4 × 4GB DDR3-1333
non-ECC, two of them an unbranded mix.

Worse, **corruption that happens on write is baked in**. The 19 damaged spots
in `tape01.mkv` reproduced on the Mac too, and 19GB had to be rebuilt.

The response was to limit the Ubuntu box to capture and decode and do
everything from export onwards on the Mac (`vhsfinish`). If you are doing long,
large jobs on non-ECC memory, the first thing to check is **whether the
mismatch positions move between repeated reads of the same file**.

---

### 10. The Mac's ffmpeg has no libsoxr, and `asetrate` truncates to an integer

Clock-drift correction tripped over this twice.

```sh
# ✗ Homebrew's ffmpeg is not built with --enable-libsoxr
#   Requested resampling engine is unavailable
-af "asetrate=47985,aresample=48000:resampler=soxr"

# ✓ use the standard swr
-af "aresample=48000:filter_size=128"
```

On top of that, `asetrate` **truncates to an integer** even when given a
decimal. Measured: `asetrate=47985` and `asetrate=47984.99` both returned
60.018771 seconds for a 60-second input. Stepping at 48kHz gives a step size of
20.8ppm = 0.075 s/hour, which is 4.5 frames over a two-hour tape.

Multiply by ten first and the step drops to 2.08ppm.

```sh
-af "aresample=480000,asetrate=479850,aresample=48000:filter_size=128"
```

---

## Settings determined by measurement

### RF capture gain

| level | 6dB | over 100 IRE | clipped at ceiling | dropped fields |
|---|---|---|---|---|
| 31 | ON | 18.28% | - | 12 |
| 31 | OFF | 8.97% | 1.26% | 0 |
| **24** | **ON** | **1.49%** | **0.88%** | **0** |
| 20 | ON | 18.00% | 1.17% | 61 |
| 16 | ON | 21.17% | 1.24% | 1 |

**`vmux=2 / level=24 / sixdb=1` is optimal.** It gets worse in both
directions.

### Quality reached

```
Flat-field noise       0.90 IRE  (SNR about 41dB)
White sparkles         0.003%
Chroma / rainbow ratio 91.2
```

### When the colour will not come out, try this first

**Stop the deck and start playback again.**

A colour-burst SNR of only `+4.0 dB`, buried in rainbow noise, became
`+33.1 dB` from nothing more than restarting playback. Presumably the tracking
re-locks.

None of the following made any difference, so do not start there:

- 10-bit mode (`tenbit=1`) … +4.0 → +3.1 dB (worse; it is not quantisation noise)
- `--ntsc-phase-comp` / `--chroma-nr` / `ntsc3d` / `--chroma-gain` … the numbers do not move at all
- Tape speed `--ts SP/LP/SLP` … all three give identical values
- Grounding the coax … **helps luma** (sparkles 0.92% → 0.22%) but leaves chroma unchanged

---

## Usage

```sh
vhstool check            Check the environment (devices, free space, signal level)
vhstool rec NAME [SEC]   Capture RF and the reference simultaneously
vhstool build NAME       Decode → colourise → merge audio
vhstool auto NAME [SEC]  rec and build together
vhstool watch [NAME]     Wait for a signal, then capture and finish automatically
vhstool list             List captures

vhsdeliver NAME [PROFILE]  Produce a delivery MP4 from a preservation master
vhsverify FILE [MASTER]    Check a deliverable against the spec (15 items)
```

On the Mac (export through delivery):

```sh
vhsfinish NAME             Nine stages from the RF on the NAS to deliverables
vhsfinish NAME --status    How far it got
vhsfinish NAME --from STAGE  Redo from that stage
vhsfinish NAME --yes       Continue even if sync fails (not recommended)
vhsclean NAME              Remove intermediates
vhsclean NAME --rf         Also delete the original RF (verifies outputs, makes you type the name)

setup-mac.sh verify        Confirm the required tools are present
```

Storage is split across separate NAS shares (not folders under `home`).

```sh
VHS_NAS_DIR=/Volumes/rf_tmp        # Original RF, reference capture, intermediates, review clips
VHS_MKV_DIR=/Volumes/rf_mkv        # Preservation masters (.mkv)
VHS_MP4_DIR=/Volumes/rf_mp4        # Delivery MP4s
```

Masters get renamed to the title of the work. Once renamed, hand the file
itself to the tool and the deliverables can be rebuilt; the output name is
derived from the master's name.

```sh
vhsdeliver "/Volumes/rf_mkv/[GLAY]VIDEO GLAY 2.mkv" standard-v1
# → /Volumes/rf_mp4/[GLAY]VIDEO GLAY 2_standard.mp4
```

`watch` is the easy path: start it, walk away, and **just press Play on the
deck**.

1. Poll the RF level once a second
2. Three consecutive detections → start capturing (RF and reference together)
3. 15 seconds of silence → stop automatically (end of tape)
4. Carry straight on through decode → colourise → merge audio

```sh
VHS_THRESHOLD=4.0 vhstool watch tape01   # detection sensitivity
VHS_OFF_COUNT=30  vhstool watch tape01   # seconds of silence before stopping
VHS_V4L_INPUT=0   vhstool rec tape01 60  # 0=Composite 1=S-Video (default 1)
```

The input connector and video standard are configured afresh on every capture,
so swapping cables needs no change on the `vhstool` side.

### What is automated on the Mac

`vhsfinish` runs nine stages in order and records each completion in
`mac_<NAME>/.state/<stage>.done`. After a crash it skips what is already done,
so a decode that takes hours is never repeated by accident.

| Stage | What it does | When it stops |
|---|---|---|
| check | Verify input and free space (2.5× the RF) | Aborts if short |
| decode | RF → TBC | |
| export | Colourise → video.mkv | |
| crc | Re-read every frame | Aborts on a single mismatch |
| align | Measure sync with six 30-second windows | |
| (decision) | Spread within one frame and at least four windows | Stops otherwise (`--yes` overrides) |
| merge | Merge audio → preservation master | **Always stops if a master already exists** |
| range | Correct to `color_range=pc` | |
| deliver | Standard and contrast variants + automated checks | Aborts if the checks fail |

The unattended pass/fail decision is based on **the spread between windows**,
not on a self-reported confidence value. An earlier whole-series correlation
confidently returned an answer that was 0.46 s (14 frames) wrong, so nothing
here trusts a single metric.

Not overwriting the master is deliberate. To rebuild one, a human moves it
aside by hand.

```sh
mv "/Volumes/rf_mkv/master_tape02.mkv" "/Volumes/rf_mkv/old_master_tape02.mkv"
vhsfinish tape02 --from merge
```

### What a human still has to do

Only three things cannot be automated.

1. Put the tape in and press Play
2. Watch the three clips in `_review` on a playback machine (especially the
   third one, for audio drift that grows towards the end)
3. Watch at least one deliverable all the way through

The third cannot be skipped. `vhsverify` only looks for things broken by a
misconfiguration or an accident; no machine can tell you whether shadow detail
has been thrown away.

### Output formats

```
tape01.mkv
  video  FFV1 (lossless, interlacing preserved)
  audio  FLAC 16-bit/48kHz (lossless)
```

MKV is used because of AVI's 4GB limit (OpenDML extends it, but it is awkward),
AVI's poor timestamp representation, and because FFV1 + Matroska is the
standard archival combination.

If you work with music material, do not make the audio lossy. The reference
capture `ref.mkv` holds its audio as FLAC, so redoing only the final merge
rebuilds the sound — no re-decode required.

### Producing deliverables (preservation and delivery are separate)

The preservation master is kept **unprocessed**; cosmetic adjustment is applied
**only to the deliverable**. That separation is the whole point of the RF
archive approach: you never have to sacrifice the original for the sake of how
the delivery looks.

```sh
vhsdeliver tape01              # standard (standard-v1)
vhsdeliver tape01 contrast-v1  # contrast-oriented
```

| | Contents |
|---|---|
| Preservation master | FFV1, unprocessed, full range, 10-bit |
| Standard delivery | H.264 CRF18 / black point 68 / light NR / converted to limited range |
| Contrast-oriented | As above, black point 84 (an option for customers who prefer the look) |

Two choices — "standard" and "contrast" — are enough for a customer. There is
no need to make them pick technical parameters such as a black point value.

#### The parameters are frozen

The values live in [`profiles/standard-v1.sh`](profiles/), not in the scripts.
**Adjusting parameters on every job destroys reproducibility**, so a change
means creating a new profile version and putting it through the same
verification before adopting it.

The verification record is [`docs/verify-standard-v1.en.md`](docs/verify-standard-v1.en.md).

#### Why the black point is 68

Export is full range (black = 0), so lowering the black point means deciding
what percentage of the bottom end gets pushed to 0. This was measured on scenes
containing black subjects.

| Black point | Of the crushed pixels, those forming runs of 10 or more ("structure") |
|---|---|
| 68 | 2.3–2.4% (about 0.02% of the frame) |
| 84 | **17.1–25.9%** (shading in a suit, strands of hair) |
| 107 | Crushes 9.6% of the whole programme — out of the question |

Isolated one- or two-pixel hits are noise troughs, not structure. **The crush
percentage alone is not enough; you have to look at the shape of what was
lost.**

As the default for a preservation service, not discarding shadow detail
carelessly matters more than making blacks look deep.

#### Always run the automated check after producing output

```sh
vhsverify /Volumes/rf_mp4/tape01_standard.mp4 /Volumes/rf_mkv/master_tape01.mkv
```

Stream layout, codec, `color_range`, resolution, frame rate, duration and
start time, faststart, decode errors across the whole file, and an audio
waveform comparison against the master — 15 items in total. `vhsdeliver` calls
this automatically at the end.

It is not a substitute for watching the result; it is **a gate that keeps
accidents and misconfigurations from shipping**.

### Transferring to the NAS

When `build` finishes it transfers the result to the NAS automatically
(`VHS_NAS_DIR`, default `/mnt/rftmp`). Sizes are compared afterwards, and a
mismatch is treated as a failure.

The NAS is in fstab with `nofail,_netdev,x-systemd.automount`, so boot is not
held up when the NAS is down and the share mounts on first access. Credentials
live in `/etc/vhs-nas.cred` (mode 600, root only) and never appear on a command
line.

### Capacity planning for bulk work

```
One 20-minute tape = RF 34GB + TBC 69GB + master 25GB = 128GB
```

```sh
vhstool clean NAME        # delete the TBC intermediates (about 69GB)
vhstool clean NAME all    # also delete rf.u8, after size-matching the master on the NAS
```

`all` **will not delete rf.u8 until it has confirmed the finished file reached
the NAS**. If you never intend to re-decode, `all` brings a tape down to 25GB.

Keep rf.u8 only if you might re-decode. `flac` compresses it to roughly half.

### How interlacing is handled

On the RF side, `tbc-video-export` keeps the interlacing in FFV1 (`tff`), and
the finished file is `-c:v copy`, so it stays. **Nothing is deinterlaced.**

A preservation master keeps the original information and leaves presentation to
the player. VLC and mpv deinterlace on playback.

### Doing one tape overnight

```sh
# rewind the tape first
vhstool watch tape01          # start waiting
# → press Play on the deck and go to bed
# → it stops itself at the end of the tape and runs on through decode
```

One 20-minute tape uses about **128GB** of disk (RF 34 / TBC 69 / master 25).
Against 231GB free that is **one tape at a time**, so clear the intermediates
the next morning.

```sh
vhstool clean tape01          # frees about 69GB of TBC; master and rf.u8 remain
```

A 20-minute tape decodes in about **3.6 hours** (11× real time).

A long silent stretch will stop the capture, so extend it with something like
`VHS_OFF_COUNT=30` for tapes with gaps.

### Always verify after producing the output

A sync calculation stays correct even when you apply it the wrong way round,
which means you cannot notice from the numbers. The sign of `-itsoffset` was
applied backwards once; the result was a finished file with audio about nine
seconds late, built over five hours and transferred 20GB to the NAS before an
ear caught it.

Two guards exist because of that:

1. **The variable is named after what it does.** Not `offset_sec` (which
   direction is it off?) but `trim_sec` (how many seconds to cut from the head
   of the reference). Since the method is `-ss` on the head, there is no sign
   to get backwards.
2. **The output checks itself.** After muxing, the audio track's `start_time`
   is read back and anything beyond ±0.2 s raises a warning.

`build` also **makes three short review clips from the finished file and puts
them on the NAS**. Checking audio sync requires playing the file on a playback
machine, which requires it to be on the NAS, so this makes verification
possible without waiting for the full 20GB transfer.

### Confirming an exported file is genuinely intact

FFV1 carries a CRC per slice, so damage is detectable.

```sh
ffmpeg -v error -i output.mkv -f null - 2>&1 | grep -c "CRC mismatch"
```

When mismatches do appear, **reading the same file three times is what
separates the causes.**

| Positions between reads | Meaning |
|---|---|
| **Different every time** | The file is fine; the read path (usually memory) is corrupting it |
| **Identical every time** | The file itself is damaged; it was already wrong when written |

That test is what led to the faulty RAM in the capture machine.

```
Reading the same file three times
  1st  775.275s                      1 hit
  2nd  888.154s / 184.785s           2 hits
  3rd  171.171s ×2 / 1105.671s       3 hits
```

**Not one position overlaps.** SATA transfer errors (`UDMA_CRC_Error_Count`)
were 0 and uncorrectable SSD errors were 0, so the corruption happens after the
data leaves the SSD — in memory. The machine had non-ECC DDR3 with **two
different part numbers, two sticks each**, filling all four slots.

The awkward part is that **there are two distinct failure modes**:

- **On write** → baked into the file. **Permanently unrecoverable**
- **On read** → a different place corrupts on every read; the file is fine

The same root cause produces different symptoms, which is confusing until you
separate them. On a machine with suspect memory, **stop at decode and export on
a different machine.** As long as the original RF and the TBC survive, the
finished file can always be rebuilt.

### How sync works

The RF side and the reference side run on **separate clocks**, so a long
recording always drifts.

1. Reduce both videos to 32×24 greyscale and build a per-frame mean-luma series
2. Take the cross-correlation peak as the **frame-level offset**
3. Compare against the second-highest peak to **self-report a confidence**
4. Measure the offset separately in the first and second halves; the difference
   gives the **clock drift**

**Never derive the drift from the ratio of total durations.** That mistakes a
difference in capture start time for drift (it produced an impossible 1.25× in
practice).

Drift is **not applied** if either of these holds:

- Correlation in the leading or trailing window is below 0.35 (too little
  picture change to localise)
- The computed value falls outside ±0.5% (impossible for a crystal difference)

In practice both sides hold 29.97fps to better than 0.01%, so **drift
correction is almost never needed**. No correction is far safer than a wrong
one.

→ [`bin/vhsalign.py`](bin/vhsalign.py)

### Rough performance

```
Capture  28.6 MB/s (uncompressed, about 103GB/hour)
Decode   2.8 FPS = about 0.09× real time
         → about 22 hours for a two-hour tape
```

---

## Manual commands

```sh
# capture
cat /dev/cxadc0 | pv > /mnt/rf/tape.u8

# decode (pass 28.636363 to -f; the 40MHz default will fail)
vhs-decode --tf VHS --system NTSC -f 28.636363 -t 8 /mnt/rf/tape.u8 /mnt/rf/tape

# colourise (it pairs luma and chroma automatically; calling
#            tbc-chroma-decoder directly will not pick up _chroma.tbc)
tbc-video-export --threads 8 --chroma-decoder ntsc3d /mnt/rf/tape.tbc /mnt/rf/tape_out
```

---

## Tap points (JVC decks)

| | |
|---|---|
| Video RF | **TP106 "PB FM"** |
| HiFi audio RF | **TP2253 "A.PB FM"** |

The same on HR-S7500 / HR-S2912I / HR3800U / SR-MV45 — JVC's standard layout.

A 0.01µF coupling capacitor is fine (into 75Ω that is a 212kHz corner, and only
0.47dB of attenuation at 629kHz). Always connect the coax ground.

---

## Licence

This repository's own work (`bin/`, `config/`, `docs/`) is MIT.

`patches/` are diffs against upstream projects and follow the licence of what
they apply to.

- [cxadc-linux3](https://github.com/happycube/cxadc-linux3) — GPLv2
- [vhs-decode](https://github.com/oyvindln/vhs-decode) — GPLv3
- [tbc-tools](https://github.com/harrypm/tbc-tools) — GPLv3
- [GV-USB2-Driver](https://github.com/Isaac-Lozano/GV-USB2-Driver) — GPLv2
