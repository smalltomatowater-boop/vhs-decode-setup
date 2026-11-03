***日本語** · [English](flow.en.md)*

# 処理フロー（コピペ用）

2026-11-02 現在。1本のテープを納品物にするまでの全工程。

収録とデコードは Ubuntu 機、書き出し以降は Mac で行う。
分担の理由は Ubuntu 機の**メモリ不良**（後述）。

```
■ Ubuntu機 192.168.128.214 ── 収録とデコードまで
  vhstool check              環境チェック（デバイス・容量・信号レベル）
  vhstool watch tape02       再生ボタン待ち → 収録 → 自動で仕上げ
  vhstool rec tape02 7200    時間指定で収録だけ
  vhstool push tape02        NASへ転送
  ※ この機では書き出しをさせない

■ NAS 192.168.128.120 ── 共有が3つ。home の下のフォルダではない
  /Volumes/rf_tmp   作業用
      rf_tape02.u8       原本RF
      ref_tape02.mkv     参照キャプチャ（音声源・同期の基準）
      mac_tape02/        中間ファイル（TBC・video.mkv・.state）
      _確認用/            20秒クリップ
  /Volumes/rf_mkv        保存マスター(.mkv)
  /Volumes/rf_mp4        納品MP4

■ Mac ── 書き出し以降
  vhsfinish tape02           これ1本で納品物まで
    1 check    入力と容量の確認（RFの2.5倍の空きが必要）
    2 decode   RF → TBC
    3 export   カラー化 → video.mkv
    4 crc      全フレーム読み直し
    5 align    30秒窓×6で同期を測る
    6 判定     ばらつき1コマ以内 かつ 窓4個以上なら通過／外れたら停止
    7 merge    音声合体 → 完成_tape02.mkv（既にあれば必ず止まる）
    8 range    color_range=pc に修正（メタデータのみ・無劣化）
    9 deliver  納品_標準 / 納品_コントラスト重視 ＋ 自動検査15項目
    clips      確認用20秒×3本

  vhsfinish tape02 --status       進捗だけ見る
  vhsfinish tape02 --from align   align からやり直す
  vhsfinish tape02 --yes          同期が不合格でも進める（非推奨）
  vhsclean tape02                 中間を削除（成果物を照合してから）
  vhsclean tape02 --rf            原本も削除（名前を打たせる）

■ 人がやること
  テープを入れて再生を押す
  確認用3本を見る（特に3本目で音ズレが増えていないか）
  納品物を1本は通して目で見る
```

## 成果物

| 置き場 | ファイル | |
|---|---|---|
| `rf_tmp` | `rf_<名前>.u8` | 原本RF。これがある限り何度でもやり直せる |
| `rf_tmp` | `_確認用/` | 20秒×3本。音ズレ確認用 |
| `rf_mkv` | `完成_<名前>.mkv` | 保存マスター。FFV1 + FLAC・無加工・フルレンジ |
| `rf_mp4` | `<名前>_標準.mp4` | H.264 640x480 CRF18 + AAC 192k |
| `rf_mp4` | `<名前>_コントラスト重視.mp4` | 同上・黒点84 |

置き場は環境変数で変えられる。

```sh
VHS_NAS_DIR=/Volumes/rf_tmp   # 作業用
VHS_MKV_DIR=/Volumes/rf_mkv        # 保存マスター
VHS_MP4_DIR=/Volumes/rf_mp4        # 納品MP4
```

## 改名した後にやり直すとき

マスターは作品名に改名して運用する。`vhsfinish` は作った時点のパスを
`mac_<名前>/.state/master.path` に控えるので、改名しなければそのまま追える。
改名したら、ファイルそのものを渡せばいい。

```sh
vhsdeliver "/Volumes/rf_mkv/[GLAY]VIDEO GLAY 2.mkv" standard-v1
```

出力名はマスターの名前から作られる（`完成_` の接頭辞は落とす）。
上の例なら `[GLAY]VIDEO GLAY 2_標準.mp4` になる。

## 工程マーカー

`vhsfinish` は `mac_<名前>/.state/<工程>.done` に完了時刻を置く。
落ちても済んだ工程は飛ばすので、数時間かかるデコードをやり直さない。

```sh
vhsfinish tape02 --status          # どこまで済んだか
vhsfinish tape02 --from export     # export 以降をやり直す
```

マスター `完成_<名前>.mkv` が既にあると merge 工程で必ず止まる。
作り直すなら人が手で退避させる（事故で保存マスターを失わないため）。

## 2台に分けている理由

Ubuntu 機（4GB×4枚 DDR3-1333 非ECC、うち2枚は型番不明）は
書き出し時に静かにビットを壊す。

- 同じファイルを3回読むと **CRC不一致の位置が毎回変わる**（＝読み出し経路が壊している）
- `tape01.mkv` は19か所の破損が Mac でも再現 → **書き込み時に焼き付いた永久破損**
- ドロップアウト補修数は Mac/Ubuntu で 18338箇所と完全一致 → **デコード自体は正常**
- SATA転送エラー0、SSD訂正不能0 → メモリが最有力

よって Ubuntu はデコードまで、書き出しは Mac。
メモリを交換したら3回読み検査で確認してから元に戻す。
