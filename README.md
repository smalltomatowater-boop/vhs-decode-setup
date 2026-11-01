# vhs-decode-setup

VHSテープを **RF信号から直接デコード** する環境の構築記録と自動化ツール。

2011年製の中古PCに Ubuntu 24.04 を入れ、CXカードで生のFM信号を吸い出し、
`vhs-decode` でカラー映像まで復元するまでの全手順。

---

## このリポジトリ固有の中身

デコード本体は上流（[cxadc](https://github.com/happycube/cxadc-linux3) /
[vhs-decode](https://github.com/oyvindln/vhs-decode) /
[tbc-tools](https://github.com/harrypm/tbc-tools)）の成果。
ここにしか無いのは次の2つ。

### 1. 再生ボタンを押すだけで完結する収録

```sh
vhstool watch tape01
```

RFレベルを1秒ごとに監視し、**信号を検出したら自動で収録を開始**、
**テープが終われば自動で停止**して、そのままデコード・カラー化・
音声合体・NAS転送まで走る。人間の操作は再生ボタンだけ。

収録と同時に通常のキャプチャ（映像＋音声）も回し、
**2つの映像を相互相関で突き合わせて音声を同期**させる。

### 2. GV-USB2 を新しいカーネルで動かすパッチ

I-O DATA GV-USB2（日本で広く出回っているアナログキャプチャ）は、
現行カーネルではビルドも動作もしない。

| 症状 | 原因 |
|---|---|
| `'const struct vb2_ops' has no member named 'wait_prepare'` | Linux 6.10 で vb2 のコールバックが削除された |
| `urb submit failed (-11)` / `swiotlb buffer is full (sz: 786432 bytes)` | **USB帯域不足ではない。** swiotlb の1回あたり上限 256KB を超える DMA 要求 |

後者は **EHCI（USB2.0世代）× メモリ4GB超 × IOMMU無し** でのみ発生する。
VHSデジタル化のために古いPCを用意すると踏みやすい組み合わせ。

→ [`patches/`](patches/) ／ 上流への報告文は
[`docs/upstream-report-gvusb2.md`](docs/upstream-report-gvusb2.md)

---

## 構成

| | |
|---|---|
| PC | Dell Vostro 460 / Core i7-2600 (4C8T) / 16GB / Ubuntu 24.04.4 LTS |
| カーネル | 7.0.0-42-generic |
| RFキャプチャ | Conexant CX23880 (PCI) + [cxadc](https://github.com/happycube/cxadc-linux3) |
| 参照キャプチャ | I-O DATA GV-USB2 (USB) + [GV-USB2-Linux](https://github.com/harrypm/GV-USB2-Linux) |
| デッキ | ビクター HR-VX100 |
| 収録先 | 内蔵SATA SSD 238GB を ext4 で専用化（実測 397MB/s） |

### 信号の流れ

```
          ┌─ TP106 (PB FM) ──→ CX23880 ──→ cxadc ──→ vhs-decode ──→ 映像
VHSデッキ ─┤
          └─ AV出力 ────────→ GV-USB2 ──→ v4l2/ALSA ──→ 音声 ＋ 同期の基準
                                                            │
                                              合体 ─────────┘
```

映像はRF経由、音声は通常のAV出力から取る。
参照キャプチャの**映像**は捨てずに、RF側との**同期合わせの基準**として使う。

---

## ハマった箇所（重要）

同じ構成を再現する人は、ここだけ読めば足りる。

### 1. cxadc のパラメータは modprobe.d では設定できない

`vmux` / `level` / `sixdb` は**モジュールパラメータではなく独自の sysfs 属性**。
`modinfo cxadc` の `parm:` は空っぽ。

```sh
# ✗ 効かない
options cxadc vmux=2 level=24 sixdb=1

# ✓ udev の ATTR で設定する
KERNEL=="cxadc0", SUBSYSTEM=="cxadc", ATTR{device/parameters/vmux}="2", ...
```

→ [`config/cxadc.rules`](config/cxadc.rules)

### 2. vhs-decode は Rust 1.78 以上が必要

`Cargo.lock` が lockfile v4。Ubuntu 24.04 の `cargo` 1.75 では

```
error: lock file version 4 requires `-Znext-lockfile-bump`
```

`edition` ではなく **lockfile のバージョン**を見ること。`rustup` で stable を入れる。

### 3. ld-chroma-decoder は移動・改名している

`vhs-decode` にも `happycube/ld-decode` にも**存在しない**（公式Wikiの記述は古い）。

```
ld-chroma-decoder  →  tbc-chroma-decoder
場所: https://github.com/harrypm/tbc-tools
```

### 4. tbc-tools は ONNX Runtime の Linux SDK が要る

リポジトリの `external/onnxruntime/` には **Windows版しか入っていない**。
無効化オプションも無い（`FATAL_ERROR`）。Microsoft公式のLinux版を落として渡す。

### 5. tbc-tools は flac 1.5.0 を要求するが Ubuntu 24.04 は 1.4.3

要求しているのは `src/ld-lds-converter`（LaserDisc専用）だけで、
他のどのツールもこれに依存していない。構成から外せばよい。

→ [`patches/tbc-tools-01-skip-ld-lds-converter.patch`](patches/)

### 6. GV-USB2 ドライバが新しいカーネルでビルドできない／動かない

**(a) vb2 のコールバック削除**（Linux 6.10 以降）

```
error: ‘const struct vb2_ops’ has no member named ‘wait_prepare’
```

`vb2q->lock` を設定済みなので vb2 が自前でロックする。2行消すだけ。

**(b) swiotlb の1回あたり上限超過** ← これが厄介

```
ehci-pci: swiotlb buffer is full (sz: 786432 bytes)
gvusb2-vid: urb submit failed (-11)
```

USB帯域不足**ではない**。スロットは余っていた。

- EHCI は 32bit DMA しかできない
- このマシンは 16GB メモリ → 4GB超の領域は swiotlb バウンスバッファ経由
- swiotlb の1回あたり上限は **256KB**
- ドライバの要求は `0x100 packets × 0xc00 bytes = 786432 bytes` = **3倍オーバー**

H67 チップセットには VT-d（IOMMU）が無いので回避できない。
パケット数を 1/4 にして URB 数を倍にする。

**「USB2.0世代のPC」かつ「メモリ4GB超」でしか踏まない地雷。**

→ [`patches/gvusb2-02-swiotlb-urb-size.patch`](patches/)

---

## 実測で決めた設定値

### RFキャプチャのゲイン

| level | 6dB | 100IRE超え | 天井張付き | フィールド落ち |
|---|---|---|---|---|
| 31 | ON | 18.28% | - | 12 |
| 31 | OFF | 8.97% | 1.26% | 0 |
| **24** | **ON** | **1.49%** | **0.88%** | **0** |
| 20 | ON | 18.00% | 1.17% | 61 |
| 16 | ON | 21.17% | 1.24% | 1 |

**`vmux=2 / level=24 / sixdb=1` が最適。** 上げても下げても悪化する。

### 到達した画質

```
平坦部ノイズ        0.90 IRE  (SNR 約41dB)
白スパークル        0.003%
彩度 / 虹ノイズ比   91.2
```

### 色が出ないときにまず試すこと

**デッキを一度停止して再生し直す。**

カラーバーストSNRが `+4.0 dB` しか無く虹ノイズに埋もれていた状態が、
再生し直しただけで `+33.1 dB` になった。トラッキングの再ロックと思われる。

以下はすべて**効果が無かった**ので先に疑わないこと。

- 10bitモード (`tenbit=1`) … +4.0 → +3.1 dB（むしろ悪化。量子化ノイズではない）
- `--ntsc-phase-comp` / `--chroma-nr` / `ntsc3d` / `--chroma-gain` … 数値が1ミリも動かない
- 録画速度 `--ts SP/LP/SLP` … 3つとも同一値
- 同軸のグランド接続 … **輝度には効く**（スパークル 0.92% → 0.22%）が色は不変

---

## 使い方

```sh
vhstool check            環境チェック（デバイス・空き容量・信号レベル）
vhstool rec 名前 [秒]     RFと参照キャプチャを同時収録
vhstool build 名前        デコード→カラー化→音声合体
vhstool auto 名前 [秒]    rec と build をまとめて
vhstool watch [名前]      信号を待ち受け、再生を検出したら自動で収録＆仕上げ
vhstool list             収録一覧
```

いちばん楽なのは `watch`。これを起動して放置し、**デッキの再生ボタンを押すだけ**。

1. 1秒ごとにRFレベルを監視
2. 3回連続で信号検出 → 自動で収録開始（RF＋参照を同時）
3. 15秒無信号が続いたら自動停止（テープ終了）
4. そのままデコード → カラー化 → 音声合体まで

```sh
VHS_THRESHOLD=4.0 vhstool watch tape01   # 検出感度
VHS_OFF_COUNT=30  vhstool watch tape01   # 停止までの無信号秒数
VHS_V4L_INPUT=0   vhstool rec tape01 60  # 0=Composite 1=S-Video（既定1）
```

収録のたびに入力端子と映像規格を設定し直すようにしてある。
挿し替えても `vhstool` 側の設定は不要。

### 出力フォーマット

```
tape01.mkv
  映像  FFV1（可逆・インターレース保持）
  音声  FLAC 16bit/48kHz（可逆）
```

MKV を使う理由は、AVI の 4GB 問題（OpenDML で延長はできるが扱いが面倒）、
AVI のタイムスタンプ表現が貧弱なこと、そして FFV1 + Matroska が
アーカイブの標準的な組み合わせであること。

音楽ものを扱うなら音声を非可逆にしないこと。参照キャプチャ `ref.mkv` は
音声を FLAC で持っているので、最終合体だけやり直せば音は作り直せる
（デコードのやり直しは不要）。

### NASへの転送

`build` が終わると完成品を自動で NAS に転送する（`VHS_NAS_DIR`、既定
`/mnt/nas/VHS_RF`）。転送後にサイズを照合し、一致しなければ失敗として扱う。

NAS は `nofail,_netdev,x-systemd.automount` で fstab に登録してあるので、
NAS が落ちていても起動は止まらず、アクセス時に自動でマウントされる。
認証情報は `/etc/vhs-nas.cred`（600, root のみ）に置き、
コマンドラインには載せない。

### 大量にやるときの容量方針

```
20分テープ1本  = RF 34GB + TBC 69GB + 完成品 25GB = 128GB
```

```sh
vhstool clean 名前        # TBC中間を削除（約69GB）
vhstool clean 名前 all    # NAS上の完成品とサイズ照合した上で rf.u8 も削除
```

`all` は **NAS に完成品が届いていることを確認してからでないと rf.u8 を
消さない**。再デコードする予定が無いなら `all` で 1本あたり 25GB まで減る。

再デコードしたい場合だけ rf.u8 を残す。`flac` で約半分に圧縮できる。

### インターレースの扱い

RF側は `tbc-video-export` が FFV1 でインターレースのまま保持する（`tff`）。
完成品も `-c:v copy` なのでそのまま。**デインターレースはしない。**

保存用マスターは元の情報を捨てずに持ち、見せ方は再生ソフトに任せる。
VLC や mpv は再生時にデインターレースする。

### 一晩で1本やる手順

```sh
# テープを巻き戻しておく
vhstool watch tape01          # 待ち受け開始
# → デッキの再生ボタンを押して寝る
# → テープが終わると自動停止し、そのままデコードまで走る
```

20分テープ1本でディスクを **約128GB** 使う（RF 34 / TBC 69 / 完成品 25）。
231GBの空きに対して**1本で精一杯**なので、翌朝に中間ファイルを片付ける。

```sh
vhstool clean tape01          # TBC約69GBを解放。完成品と rf.u8 は残る
```

デコードは20分テープで **約3.6時間**（実時間の11倍）。

無信号が続くと停止するので、長い空白があるテープは
`VHS_OFF_COUNT=30` のように延ばすこと。

### 同期のしくみ

RF側と参照側は**別のクロック**で動くため、長時間録ると必ずズレる。

1. 両方の映像を 32×24 のグレースケールに潰し、1フレームごとの平均輝度の時系列を作る
2. 相互相関のピーク位置から**フレーム単位のオフセット**を求める
3. 2位のピークとの比を見て**信頼度を自己申告**する
4. 前半と後半で別々にズレを測り、その差から**クロックドリフト**を求める

**全体の再生時間の比でドリフトを出してはいけない。** 収録開始の
タイミング差をドリフトと誤認する（実測で1.25倍という有り得ない値が出た）。

ドリフトは次のどちらかに当てはまれば**適用しない**:

- 前後の窓の相関が 0.35 未満（映像の変化が乏しく位置を特定できていない）
- 算出値が ±0.5% を外れる（水晶の差としては有り得ない）

実際、RF側と参照側はどちらも 29.97fps を誤差0.01%未満で保っており、
**ドリフト補正はほぼ常に不要**だった。誤った補正を当てるくらいなら
無補正のほうがはるかに安全。

→ [`bin/vhsalign.py`](bin/vhsalign.py)

### 性能の目安

```
収録    28.6 MB/s（無圧縮 約103GB/時）
デコード 2.8 FPS = 実時間の約0.09倍
        → 2時間テープで 約22時間
```

---

## 手動コマンド

```sh
# 収録
cat /dev/cxadc0 | pv > /mnt/rf/tape.u8

# デコード（-f に 28.636363 を渡すこと。既定の40MHzのままだと失敗する）
vhs-decode --tf VHS --system NTSC -f 28.636363 -t 8 /mnt/rf/tape.u8 /mnt/rf/tape

# カラー化（輝度と色のペアを自動認識する。
#           tbc-chroma-decoder を直接呼ぶと _chroma.tbc を拾わない）
tbc-video-export --threads 8 --chroma-decoder ntsc3d /mnt/rf/tape.tbc /mnt/rf/tape_out
```

---

## タップ点（JVC機）

| | |
|---|---|
| 映像RF | **TP106「PB FM」** |
| HiFi音声RF | **TP2253「A.PB FM」** |

HR-S7500 / HR-S2912I / HR3800U / SR-MV45 いずれも同じ。JVCの標準配置。

結合コンデンサは 0.01µF で問題ない（75Ω負荷で遮断212kHz、629kHzの減衰は0.47dB）。
同軸のグランドは必ず繋ぐこと。

---

## ライセンス

このリポジトリ自身の成果物（`bin/`, `config/`, `docs/`）は MIT。

`patches/` は各上流プロジェクトへの差分であり、適用先のライセンスに従う。

- [cxadc-linux3](https://github.com/happycube/cxadc-linux3) — GPLv2
- [vhs-decode](https://github.com/oyvindln/vhs-decode) — GPLv3
- [tbc-tools](https://github.com/harrypm/tbc-tools) — GPLv3
- [GV-USB2-Linux](https://github.com/harrypm/GV-USB2-Linux) — GPLv2

---

## English summary

Tooling and patches for capturing VHS tapes via RF (software decoding with
`vhs-decode`) on a 2011-era PC running Ubuntu 24.04 / kernel 7.0.

Two things here are not available upstream:

**Signal-triggered capture.** `vhstool watch` polls the cxadc RF level, starts
recording when playback is detected, stops when the tape ends, then decodes,
colourises, muxes lossless audio from a parallel reference capture (aligned by
cross-correlating the two video streams) and copies the result to a NAS.

**GV-USB2 (I-O DATA, em28xx-incompatible) on current kernels.** Two patches:

- Linux 6.10+ removed `wait_prepare` / `wait_finish` from `struct vb2_ops`,
  breaking the build. The driver already sets `q->lock`, so the callbacks are
  simply dropped.
- `urb submit failed (-11)` together with
  `swiotlb buffer is full (sz: 786432 bytes)` is **not** a USB bandwidth
  problem. On EHCI hosts with more than 4GB of RAM and no IOMMU, DMA goes
  through swiotlb bounce buffers, where a single mapping cannot exceed 256KB.
  The driver requested `0x100 packets * 0xc00 bytes = 786432 bytes`. Reducing
  packets per URB to `0x40` (and doubling the URB count) fixes it.

See [`patches/`](patches/) and
[`docs/upstream-report-gvusb2.md`](docs/upstream-report-gvusb2.md).
