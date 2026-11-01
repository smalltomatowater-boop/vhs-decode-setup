# vhs-decode-setup

VHSテープを **RF信号から直接デコード** する環境の構築記録と自動化ツール。

2011年製の中古PCに Ubuntu 24.04 を入れ、CXカードで生のFM信号を吸い出し、
`vhs-decode` でカラー映像まで復元するまでの全手順。
素直に進まなかった箇所（ビルドの壁 6個）をすべて記録してある。

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
```

### 同期のしくみ

RF側と参照側は**別のクロック**で動くため、長時間録ると必ずズレる。

1. 両方の映像を 32×24 のグレースケールに潰し、1フレームごとの平均輝度の時系列を作る
2. 相互相関のピーク位置から**フレーム単位のオフセット**を求める
3. 2位のピークとの比を見て**信頼度を自己申告**する
4. 再生時間の比から**クロックドリフト**を推定し、`asetrate` で音声を補正

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
