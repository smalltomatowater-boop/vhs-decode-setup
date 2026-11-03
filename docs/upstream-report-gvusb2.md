# Upstream report: GV-USB2 driver

Target repository: **[Isaac-Lozano/GV-USB2-Driver](https://github.com/Isaac-Lozano/GV-USB2-Driver)**
(48 stars, issues enabled). Not `harrypm/GV-USB2-Linux`, which is a fork with
issues disabled — a pull request there would reach nobody. The two source files
touched here are byte-identical between the two (verified by blob SHA), so the
patches apply unchanged.

Status checked 2026-11-03.

---

## Issue 1 — build failure on Linux 6.10+ : **already reported, do not duplicate**

- Issue [#14](https://github.com/Isaac-Lozano/GV-USB2-Driver/issues/14)
  "Compilation fails on Linux kernel 7 and above"
- PR [#13](https://github.com/Isaac-Lozano/GV-USB2-Driver/pull/13)
  `zooksman:kernel7-fix`, open since 2026-06-13

PR #13's diff is identical to
[`patches/gvusb2-01-vb2-wait-callbacks.patch`](../patches/gvusb2-01-vb2-wait-callbacks.patch):

```diff
-	.wait_prepare    = vb2_ops_wait_prepare,
-	.wait_finish     = vb2_ops_wait_finish,
```

**Do not open a competing pull request.** It has been open for months, which
usually means the maintainer cannot verify it. What helps is an independent
confirmation on different hardware. Draft comment for #13:

```markdown
Confirming this fix on different hardware.

Dell Vostro 460 (H67, i7-2600), Ubuntu 24.04.4 LTS, kernel 7.0.0-42-generic,
x86_64, I-O DATA GV-USB2 (04bb:0532).

Without the patch the build fails exactly as in #14. With it the module builds
cleanly and the device streams 720x480 UYVY at 29.97fps on both S-Video and
composite.

`gvusb2_vb2_setup()` already does `vb2q->lock = &dev->vb2q_lock;`, so videobuf2
takes the queue lock itself and the removed callbacks were redundant even on
older kernels. Locking behaviour is unchanged.
```

---

## Issue 2 — streaming fails on EHCI hosts with >4GB RAM and no IOMMU : **not reported anywhere**

Searched the upstream repository's issues and pull requests for `swiotlb`,
`urb submit failed`, `ISOCH_PACKETS`, `bounce` and `EAGAIN`: zero hits. A
GitHub-wide code search for the changed constant finds no other fork carrying
this fix. This one is worth opening.

**Open an issue first, then the pull request referencing it.** The reproduction
conditions are unusual enough that a maintainer without the hardware will want
the reasoning written down somewhere permanent.

**PR title:** `Reduce isoc URB size so DMA mappings fit the swiotlb 256KB limit`

**Body:**

```markdown
### Problem

On an older USB 2.0 (EHCI) machine with more than 4GB of RAM and no IOMMU,
streaming never starts:

```
ehci-pci 0000:00:1d.0: swiotlb buffer is full (sz: 786432 bytes), total 32768 (slots), used 66 (slots)
gvusb2-vid 2-1.3:1.0: urb submit failed (-11)
WARNING: drivers/media/common/videobuf2/videobuf2-core.c:1797 at vb2_start_streaming+0xff/0x180
```

`-11` (`EAGAIN`) looks like a USB bandwidth problem, but it is not — note that
only 66 of 32768 swiotlb slots were in use. The failure is the **size of a
single mapping**, not exhaustion.

### Cause

EHCI controllers are 32-bit DMA only. With more than 4GB of RAM and no IOMMU to
remap, buffers above the 4GB line go through swiotlb bounce buffers. A single
swiotlb mapping cannot exceed `IO_TLB_SEGSIZE * IO_TLB_SHIFT` = **256KB**.

The driver asks for:

```
GVUSB2_NUM_ISOCH_PACKETS * GVUSB2_MAX_VIDEO_PACKET_SIZE
  = 0x100 * 0xc00
  = 786432 bytes
```

which is 3x over the limit, so `usb_submit_urb()` fails for every URB.

This does not reproduce on machines with an IOMMU (no bouncing), on machines
with 4GB or less (no bouncing), or on xHCI hosts (64-bit DMA). It reproduces
reliably on USB 2.0 era hardware that has been given more memory — a fairly
common setup for VHS capture, since people often dedicate an old PC to it.

### Fix

Quarter the packets per URB and double the number of URBs, keeping roughly the
same amount of buffering while bringing each mapping under the limit:

```
GVUSB2_NUM_ISOCH_PACKETS  0x100 -> 0x40    (64 * 3072 = 196608 bytes, under 256KB)
GVUSB2_NUM_URBS           4     -> 8
```

In-flight capacity goes from 4x256 = 1024 packets to 8x64 = 512 packets
(about 64ms at 125us per isochronous packet), which is still ample, and each
URB now completes every 8ms instead of every 32ms.

### Tested on

Dell Vostro 460 (H67, i7-2600, 16GB, EHCI only, no VT-d),
Ubuntu 24.04.4 LTS kernel 7.0, I-O DATA GV-USB2 (04bb:0532).

Before: streaming never starts, every URB submit returns -11.
After: 720x480 UYVY at 29.97fps, no URB errors, S-Video and composite both work.

Note: this needs #13 applied first, otherwise the module does not build on
kernel 6.10+ and the change cannot be tested.
```

---

## Notes for submitting

- **Do not open PR 2 before #13 is resolved.** Without it the module does not
  build on a current kernel, so a reviewer cannot verify anything.
- Spell out the reproduction conditions (EHCI / >4GB / no IOMMU) in the body.
  Most reviewers will not be able to reproduce it on their own hardware.
- Doubling `GVUSB2_NUM_URBS` is the part most open to taste. If a maintainer
  objects, reducing the packet count alone is enough to make it work.
- Upstream is slow: the oldest open PR dates from 2022-01-27 and the last
  commit to master is 2020-07-28. Expect this to sit. It is still the right
  place — a report in a repository with issues enabled stays findable, which a
  fix buried in a private fork does not.
