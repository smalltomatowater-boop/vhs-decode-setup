*[日本語](flow.md) · **English***

# Pipeline (ready to copy and paste)

As of 2026-11-02. Every stage from one tape to a finished deliverable.

Capture and decode run on the Ubuntu machine; everything from export onwards
runs on the Mac. The split exists because of the Ubuntu machine's **faulty
RAM** (see the last section).

```
■ Ubuntu 192.168.128.214 ── capture and decode only
  vhstool check              Check the environment (devices, space, signal level)
  vhstool watch tape02       Wait for Play → capture → finish automatically
  vhstool rec tape02 7200    Capture only, for a fixed duration
  vhstool push tape02        Transfer to the NAS
  ※ never let this machine do the export

■ NAS 192.168.128.120 ── three shares, not folders under home
  /Volumes/rf_tmp   working files
      rf_tape02.u8       original RF
      ref_tape02.mkv     reference capture (audio source and sync reference)
      mac_tape02/        intermediates (TBC, video.mkv, .state)
      _review/           20-second clips
  /Volumes/rf_mkv        preservation masters (.mkv)
  /Volumes/rf_mp4        delivery MP4s

■ Mac ── export onwards
  vhsfinish tape02           one command, all the way to the deliverables
    1 check    Verify input and free space (2.5× the RF)
    2 decode   RF → TBC
    3 export   Colourise → video.mkv
    4 crc      Re-read every frame
    5 align    Measure sync with six 30-second windows
    6 decide   Pass if spread ≤ 1 frame and ≥ 4 windows; stop otherwise
    7 merge    Merge audio → master_tape02.mkv (always stops if one exists)
    8 range    Correct color_range=pc (metadata only, lossless)
    9 deliver  standard / contrast + 15 automated checks
    clips      three 20-second review clips

  vhsfinish tape02 --status       show progress only
  vhsfinish tape02 --from align   redo from align
  vhsfinish tape02 --yes          continue even if sync fails (not recommended)
  vhsclean tape02                 delete intermediates (after verifying outputs)
  vhsclean tape02 --rf            delete the original too (makes you type the name)

■ What a human does
  Put the tape in and press Play
  Watch the three review clips (especially the third, for growing audio drift)
  Watch at least one deliverable all the way through
```

## Outputs

| Location | File | |
|---|---|---|
| `rf_tmp` | `rf_<NAME>.u8` | Original RF. As long as this exists, anything can be redone |
| `rf_tmp` | `_review/` | Three 20-second clips for checking audio sync |
| `rf_mkv` | `master_<NAME>.mkv` | Preservation master. FFV1 + FLAC, unprocessed, full range |
| `rf_mp4` | `<NAME>_standard.mp4` | H.264 640x480 CRF18 + AAC 192k |
| `rf_mp4` | `<NAME>_contrast.mp4` | As above, black point 84 |

Locations are configurable through environment variables.

```sh
VHS_NAS_DIR=/Volumes/rf_tmp   # working files
VHS_MKV_DIR=/Volumes/rf_mkv   # preservation masters
VHS_MP4_DIR=/Volumes/rf_mp4   # delivery MP4s
```

## Redoing work after a rename

Masters get renamed to the title of the work. `vhsfinish` records the path it
created in `mac_<NAME>/.state/master.path`, so an unrenamed master is still
tracked. Once renamed, just hand the file itself to the tool.

```sh
vhsdeliver "/Volumes/rf_mkv/[GLAY]VIDEO GLAY 2.mkv" standard-v1
```

The output name is derived from the master's name (the `master_` prefix is
dropped), so the example produces `[GLAY]VIDEO GLAY 2_standard.mp4`.

## Stage markers

`vhsfinish` writes a completion timestamp to `mac_<NAME>/.state/<stage>.done`.
After a crash it skips what is already done, so a decode that takes hours is
never repeated.

```sh
vhsfinish tape02 --status          # how far it got
vhsfinish tape02 --from export     # redo from export onwards
```

If the master `master_<NAME>.mkv` already exists, the merge stage always stops.
Rebuilding means a human moves it aside by hand — so that a preservation master
is never lost to an accident.

## Why the work is split across two machines

The Ubuntu machine (4 × 4GB DDR3-1333 non-ECC, two of them of unknown make)
silently corrupts bits during export.

- Reading the same file three times gives **different CRC mismatch positions
  every time** (so the read path is corrupting it)
- The 19 damaged spots in `tape01.mkv` reproduced on the Mac too → **permanent
  damage baked in at write time**
- Dropout-correction counts matched exactly between Mac and Ubuntu at 18338 →
  **the decode itself is sound**
- SATA transfer errors 0, uncorrectable SSD errors 0 → memory is the prime
  suspect

So: Ubuntu up to decode, the Mac for export. After replacing the memory,
confirm with the three-read test before moving anything back.
