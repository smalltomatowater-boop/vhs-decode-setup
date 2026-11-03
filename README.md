***日本語** · [English](README.en.md)*

# vhs-decode-setup

VHSテープを **RF信号から直接デコード** する環境の構築記録と自動化ツール。

2011年製の中古PCに Ubuntu 24.04 を入れ、CXカードで生のFM信号を吸い出し、
`vhs-decode` でカラー映像まで復元するまでの全手順。

> **この文書の位置づけ**
>
> これは**特定の1台（2011年製のPC・CX23880・GV-USB2）での構築記録**であって、
> 推奨構成ではない。これから始める人は、まず本家の資料を見ること。
>
> - [VHS-Decode Wiki](https://github.com/oyvindln/vhs-decode/wiki) — 公式の手順と推奨ハードウェア
> - [MISRC-GUI](https://github.com/harrypm/MISRC-GUI) — 収録から取り込みまでの統一ワークフロー
>
> ここに価値があるとすれば、**古いハードウェアで踏む地雷の記録**のほう。
> 現行の推奨構成（MISRC・標準的なアンプ構成）は扱っていない。

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
| 参照キャプチャ | I-O DATA GV-USB2 (USB) + [GV-USB2-Driver](https://github.com/Isaac-Lozano/GV-USB2-Driver) |
| デッキ | ビクター HR-VX100 |
| 収録先 | 内蔵SATA SSD 238GB を ext4 で専用化（実測 397MB/s） |
| 仕上げ機 | Apple M4 10コア / 32GB / macOS 26.5.1（書き出し以降を担当） |
| 保管 | NAS 3.6TB（SMB・1000baseT）。共有を3つに分ける |

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

### このリポジトリの中身

```
setup.sh           Ubuntu機（収録・デコード）の構築
setup-mac.sh       Mac機（書き出し以降）の構築と検査
bin/
  vhstool          [Ubuntu] 収録からデコード、音声合体、NAS転送まで
  vhslevel.py      [Ubuntu] RFの信号レベルを見る
  vhsfinish        [Mac] 書き出しから納品物まで9工程を通す（再開可能）
  vhsclean         [Mac] 仕上げ後の中間ファイルを片づける
  vhsdeliver       保存マスターから納品用MP4を作る（プロファイル駆動）
  vhsverify        納品物の自動チェック 15項目
  vhsalign.py      RF映像と参照映像のズレを測る（窓を複数置く方式）
  vhsqa.py         工程別にどこでどれだけ失われたかを測る
profiles/
  standard-v1.sh   標準納品の凍結値（黒点68）
  contrast-v1.sh   コントラスト重視（黒点84）
config/            cxadc と GV-USB2 の設定ファイル
patches/           上流に未取り込みの修正3本
docs/
  flow.md          処理フロー全体（コピペ用）
  verify-*.md/csv  検証記録
  upstream-*.md    上流への報告ドラフト
```

2台で分担している。収録とデコードは Ubuntu 機、**書き出し以降は Mac**。
理由は Ubuntu 機のメモリ不良（「ハマった箇所」の9番）。
全体の流れは [docs/flow.md](docs/flow.md) にコピペできる形で置いてある。

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

### 7. tbc-video-export の出力はフルレンジだが、タグは `tv` で書かれる

中身は **黒=0 / 白=1023**（フルレンジ）なのに、ファイルには
`color_range=tv`（黒=64 / 白=940）と書かれる。この食い違いを放置すると、
プレーヤーは 940 以上を全部真っ白に潰して表示する。実測した素材では
**画面の20%が940以上**に居た。

```sh
# 実測した対応関係（16bitのTBC → 10bitの出力）
#   16bit 16219(=black16bIre) → 10bit 0
#   16bit 56577(≒white16bIre) → 10bit 1023
# リミテッドなら傾き 0.02186、フルなら 0.02553。実測は 0.0251〜0.0253。

# 直し方（中身は1バイトも書き換えない。19GBでも0.2秒）
mkvpropedit 完成_tape01.mkv --edit track:v1 --set colour-range=2
```

`bin/vhsdeliver` は納品物を作る前にマスターの `color_range` を確認し、
`pc` でなければ止まる。変換が二重にかかる事故を防ぐため。

**なお、この仕様のため書き出しは 100 IRE で頭打ちになる。** TBC には
+122.5 IRE まで入っているが、出力は約 +100.6 IRE で切られ、実測で
画素の **2.5%** が失われていた。ただしその78%は数画素のオーバーシュート
（輪郭のリンギング）で、本物の明るい面は22%。JSON の `white16bIre` を
動かせば余裕を持たせられる（デコードのやり直しは不要）が未検証。

### 8. `~/.local/bin` の古い `tbc-video-export` が新しいビルドを隠す

pip で入れた 0.1.8 が PATH で先に来ると、ビルドした 3.3.0 を覆い隠す。
0.1.8 は補助ツールを旧名 `ld-dropout-correct` で探すため必ず失敗する。

```
FileIOError: ld-dropout-correct not in PATH or script dir.
```

5時間かけたデコードの直後にこれで落ちた。`vhstool` は
`PATH="$BIN:$HOME/.local/bin:$PATH"` の順にしてある。

---

### 9. 非ECCメモリの不良は「デコードの失敗」に化けて見える

CRC不一致が18件→2件と再現しない。デコードのバグを疑って半日潰した。

切り分けに効いた観測はこの3つ。

```
同じファイルを3回読む          → 不一致の位置が毎回変わる（読み出し経路が壊している）
Mac で同じRFをデコードする     → 不一致 0件
ドロップアウト補修数を比べる    → 両機とも 18338箇所で完全一致
```

3つめが決定的だった。補修数が一致するなら**デコードそのものは正常**で、
壊れているのはその後ろの経路しかない。SATA転送エラー0・SSD訂正不能0なので
残るのはメモリ。4GB×4枚 DDR3-1333 非ECC、うち2枚は型番不明の寄せ集め。

さらに悪いのは、**書き込み時に壊れたものは焼き付く**こと。
`tape01.mkv` の19か所は Mac で読んでも再現した。19GBの作り直しになった。

対策として、Ubuntu機は収録とデコードまでに留め、書き出し以降は Mac で行う
（`vhsfinish`）。非ECCで長時間の大容量処理をするなら、
**同一ファイルの複数回読みで位置が動くか**を最初に見ること。

---

### 10. Mac の ffmpeg には libsoxr が無く、`asetrate` は小数を切り捨てる

クロックドリフト補正で2回踏んだ。

```sh
# ✗ Homebrew の ffmpeg は --enable-libsoxr されていない
#   Requested resampling engine is unavailable
-af "asetrate=47985,aresample=48000:resampler=soxr"

# ✓ 標準の swr を使う
-af "aresample=48000:filter_size=128"
```

さらに `asetrate` は小数を受け取っても**整数に切り捨てる**。
実測で `asetrate=47985` と `asetrate=47984.99` は 60秒入力に対して
どちらも 60.018771 秒を返した。48kHz のまま刻むと刻み幅が
20.8ppm = 0.075秒/時 になり、2時間テープで4.5コマずれる。

いったん10倍に上げてから刻めば 2.08ppm まで下がる。

```sh
-af "aresample=480000,asetrate=479850,aresample=48000:filter_size=128"
```

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

vhsdeliver 名前 [版]      保存マスターから納品用MP4を作る
vhsverify ファイル [原本]  納品物が仕様どおりか自動チェック（15項目）
```

Mac側（書き出しから納品まで）:

```sh
vhsfinish 名前            NAS上のRFから納品物まで9工程を通す
vhsfinish 名前 --status   どこまで済んだか
vhsfinish 名前 --from 工程 その工程からやり直す
vhsfinish 名前 --yes      同期が不合格でも進める（非推奨）
vhsclean 名前             中間を片づける
vhsclean 名前 --rf        原本RFも削除（成果物を照合し、名前を打たせる）

setup-mac.sh verify       必要なツールが揃っているか確認
```

置き場はNASの共有ごとに分かれている（`home` の下のフォルダではない）。

```sh
VHS_NAS_DIR=/Volumes/rf_tmp        # 原本RF・参照キャプチャ・中間・確認用
VHS_MKV_DIR=/Volumes/rf_mkv        # 保存マスター(.mkv)
VHS_MP4_DIR=/Volumes/rf_mp4        # 納品MP4
```

マスターは作品名に改名して運用する。改名したら、ファイルそのものを渡せば
納品物を作り直せる。出力名はマスターの名前から作られる。

```sh
vhsdeliver "/Volumes/rf_mkv/[GLAY]VIDEO GLAY 2.mkv" standard-v1
# → /Volumes/rf_mp4/[GLAY]VIDEO GLAY 2_標準.mp4
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

### Mac側で何が自動化されているか

`vhsfinish` は9工程を順に通し、各工程の完了を
`mac_<名前>/.state/<工程>.done` に記録する。落ちても済んだ工程は飛ばすので、
数時間かかるデコードをやり直す事故が起きない。

| 工程 | 内容 | 止まる条件 |
|---|---|---|
| check | 入力と容量（RFの2.5倍）を確認 | 足りなければ中止 |
| decode | RF → TBC | |
| export | カラー化 → video.mkv | |
| crc | 全フレーム読み直し | 1件でも不一致なら中止 |
| align | 30秒窓×6で同期を測る | |
| 判定 | ばらつき1コマ以内かつ窓4個以上 | 外れたら停止（`--yes` で越えられる） |
| merge | 音声合体 → 保存マスター | **既にマスターがあれば必ず停止** |
| range | `color_range=pc` に修正 | |
| deliver | 標準・コントラスト重視の2本＋自動検査 | 検査不合格なら中止 |

無人で通す条件を「信頼度が高い」ではなく**窓のばらつきで**判定している。
以前の全系列一括相関は 0.46秒（14コマ）ずれた答えを自信ありげに返したので、
一つの指標を信じない作りにした。

マスターを上書きしないのは意図的な設計。作り直すときは人が手で退避させる。

```sh
mv "/Volumes/rf_mkv/完成_tape02.mkv" "/Volumes/rf_mkv/旧_完成_tape02.mkv"
vhsfinish tape02 --from merge
```

### 人が必ずやること

自動化できないのは3つだけ。

1. テープを入れて再生ボタンを押す
2. `_確認用` の3本を再生用PCで見る（特に3本目で音ズレが増えていないか）
3. 納品物を1本は通して目で見る

3つめは省けない。`vhsverify` が見ているのは「設定ミスや事故で壊れていないか」
であって、暗部の構造が消えているかどうかは機械には判定できない。

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

### 納品物を作る（保存と納品を分ける）

保存マスターは**無加工**で持ち、見栄えの調整は**納品物にだけ**かける。
これがRFアーカイブ方式の利点そのもので、納品時の見栄えのために原本を
犠牲にしなくていい。

```sh
vhsdeliver tape01              # 標準版（standard-v1）
vhsdeliver tape01 contrast-v1  # コントラスト重視版
```

| | 中身 |
|---|---|
| 保存マスター | FFV1・無加工・フルレンジ・10bit |
| 標準納品 | H.264 CRF18 / 黒点68 / 軽いNR / リミテッド変換 |
| コントラスト重視 | 同上・黒点84（見栄え優先の顧客向けオプション） |

顧客に出す選択肢は「標準」と「コントラスト重視」の2つだけでよく、
黒点の数値のような技術パラメータを選ばせる必要はない。

#### パラメータは凍結してある

設定値は [`profiles/standard-v1.sh`](profiles/) に固定してあり、
スクリプト側には書いていない。**毎回パラメータを触る運用にすると
品質の再現性が無くなる**ため、変更するときは新しいバージョンの
プロファイルを作り、同じ検証を通してから採用する。

検証記録は [`docs/verify-standard-v1.md`](docs/)。

#### 黒点を 68 にした根拠

書き出しはフルレンジ（黒=0）なので、黒を沈めるとは「下位何%を 0 に
押し込むか」という操作になる。黒い被写体のある場面で実測した。

| 黒点 | つぶれた画素のうち10画素以上連続する「構造」 |
|---|---|
| 68 | 2.3〜2.4%（＝画面の約0.02%） |
| 84 | **17.1〜25.9%**（スーツの陰影・髪の束） |
| 107 | 全編の9.6%を潰すので論外 |

孤立した1〜2画素はノイズの谷であって構造ではない。**つぶれ率だけでは
判断できず、失われた画素の形を見る必要がある。**

保存サービスの標準としては、黒を締めることより暗部の情報を不用意に
捨てないことを優先する。

#### 出力後は必ず自動チェックを通す

```sh
vhsverify /Volumes/rf_mp4/tape01_標準.mp4 /Volumes/rf_mkv/完成_tape01.mkv
```

ストリーム構成・コーデック・`color_range`・解像度・フレームレート・
長さと頭出し・faststart・全編復号のエラー・原本との音声波形照合、
計15項目。`vhsdeliver` は最後にこれを自動で呼ぶ。

人が目で見る検証の代わりではなく、**設定ミスや事故で壊れたものを
出荷しないための関門**。

### NASへの転送

`build` が終わると完成品を自動で NAS に転送する（`VHS_NAS_DIR`、既定
`/mnt/rftmp`）。転送後にサイズを照合し、一致しなければ失敗として扱う。

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

### 検証は出力を作ってから必ずやる

同期の計算結果は、**使い方を間違えても計算自体は正しいまま**なので気づけない。
実際に `-itsoffset` の符号を逆に適用し、音声が約9秒遅れた完成品を
5時間かけて作り、20GBをNASへ転送したあとで耳で発覚した。

そのため現在は次の2つを入れてある。

1. **変数名を用途そのものにした。** `offset_sec`（どちらにずれているか）ではなく
   `trim_sec`（参照の先頭を何秒切り落とすか）。`-ss` で頭を切る方式なので
   符号を取り違えようがない。
2. **出力の自己検証。** 多重化後に音声トラックの `start_time` を読み、
   ±0.2秒を超えていたら警告を出す。

さらに `build` は完成品から**確認用の短いクリップを3本作ってNASに置く**。
音ズレの確認は再生用PCで再生しないとできず、そのためにはNAS上に
ファイルが無いと始まらないため、本体20GBの転送を待たずに検証できるようにしてある。

### 書き出したファイルが本当に無傷か確かめる

FFV1 はスライスごとに CRC を持つので、壊れていれば検出できる。

```sh
ffmpeg -v error -i 出力.mkv -f null - 2>&1 | grep -c "CRC mismatch"
```

ここで不一致が出たとき、**原因の切り分けには「同じファイルを3回読む」のが効く。**

| 読むたびに位置が | 意味 |
|---|---|
| **毎回変わる** | ファイルは無事。読み出し経路（主にメモリ）が壊している |
| **毎回同じ** | ファイル自体が壊れている。書き込み時点で既に傷が入っている |

実際にこの切り分けで、収録機のメモリ不良に行き着いた。

```
同じファイルを3回読んだ結果
  1回目  775.275秒                     1件
  2回目  888.154秒 / 184.785秒          2件
  3回目  171.171秒 ×2 / 1105.671秒      3件
```

**1か所も重なっていない。** SATA の転送エラー（`UDMA_CRC_Error_Count`）は 0、
SSD の訂正不能エラーも 0 だったので、SSD から出たあと＝メモリで化けている。
該当機は非ECCのDDR3で、**型番の異なるメモリが2枚ずつ混在**し、4スロット
すべてが埋まっていた。

厄介なのは**壊し方が2通りある**こと。

- **書き込み時** → 壊れたままファイルに焼き付く。**永久に直らない**
- **読み出し時** → 読むたび別の場所が化ける。ファイル自体は無事

同じ原因から別の現象が出るため、切り分けないと混乱する。
メモリが疑わしい機械では**デコードまでに留め、書き出しは別の機械でやる**。
RF原本とTBCが残っていれば、完成品はいつでも作り直せる。

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
- [GV-USB2-Driver](https://github.com/Isaac-Lozano/GV-USB2-Driver) — GPLv2

---

## English summary

**Full English documentation: [README.en.md](README.en.md)**

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
