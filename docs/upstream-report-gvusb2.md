# harrypm/GV-USB2-Linux への報告ドラフト

2つは独立した問題なので、PRも分けて出すのが通りやすい。

---

## PR 1: Fix build on Linux 6.10+ (vb2_ops wait_prepare/wait_finish removed)

**Title:** `Fix build on Linux 6.10+: drop removed vb2_ops wait_prepare/wait_finish`

**Body:**

```markdown
### Problem

The module fails to build on Linux 6.10 and newer:

```
gvusb2-v4l2.c:203:10: error: 'const struct vb2_ops' has no member named 'wait_prepare'
gvusb2-v4l2.c:203:28: error: 'vb2_ops_wait_prepare' undeclared here (not in a function)
gvusb2-v4l2.c:204:10: error: 'const struct vb2_ops' has no member named 'wait_finish'
gvusb2-v4l2.c:204:28: error: 'vb2_ops_wait_finish' undeclared here (not in a function)
```

`wait_prepare` / `wait_finish` were removed from `struct vb2_ops`. videobuf2 now
drops and reacquires `q->lock` itself, so drivers that set `q->lock` need no
callbacks at all.

### Fix

Remove the two assignments. `gvusb2_vb2_setup()` already sets

```c
vb2q->lock = &dev->vb2q_lock;
```

so the locking behaviour is unchanged.

### Tested on

Ubuntu 24.04.4 LTS, kernel 6.14 / 7.0, x86_64, I-O DATA GV-USB2 (04bb:0532).
Builds cleanly and the device streams.
```

---

## PR 2: Fix streaming failure on EHCI hosts with >4GB RAM and no IOMMU

**Title:** `Reduce isoc URB size so DMA mappings fit the swiotlb 256KB limit`

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
```

---

## 出すときの注意

- **PR 2 を先に出さない。** PR 1 が無いとそもそもビルドできないので、
  レビュアーが検証できない。
- ハードウェアが特殊なので、再現条件（EHCI / >4GB / IOMMU無し）を
  本文に明記しておくこと。手元で再現できないレビュアーが多いはず。
- `GVUSB2_NUM_URBS` を増やす方は好みが分かれるかもしれない。
  もし渋られたら、パケット数の削減だけでも機能はする。
