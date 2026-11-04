# キャプチャ機の環境スナップショット

Dell Vostro 460（`ssh ubuntu` / 192.168.128.214）の、**リポジトリに入っていない部分**の記録。
`/` が 2009年製の Intel X25-M（通電 76,849時間）なので、死んだときに
ここを見れば再構築できるようにしておく。

取得日: 2026-11-04

```
Linux taku-Vostro-460 7.0.0-42-generic #42~24.04.1-Ubuntu SMP PREEMPT_DYNAMIC
Mon Oct 19 14:43:01 UTC 2026 x86_64   /   Ubuntu 24.04 LTS
```

## ディスク

| デバイス | 型番 | 容量 | 用途 | 通電時間 | 備考 |
|---|---|---|---|---|---|
| sda | INTEL SSDSA2M080G2GC (X25-M G2) | 80GB | `/` | 76,849h | 書込 23.3TiB / 寿命残 92% / 代替セクタ 25 |
| sdb | SanDisk SD7TB3Q-256G-1006 | 256GB | `/mnt/rf` | 38,664h | **書込寿命を報告しない個体** |

SATAポートは6本中2本使用、**4本空き**。
PCIeスロットは PCIE1(x16)・PCIE3(x1)・PCIE4(x1) が空き、PCIE2(x1) に CXカード。
**PCIスロットは物理的に存在しない**（CXカードは ASM1083 ブリッジを自前で載せた PCIe x1 カード）。

`192 Unsafe_Shutdown_Count = 201`。長時間収録・デコード中の電断は
テープ1本ぶんの再生をやり直すことになるので、UPSは検討に値する。

## /etc の設定

`config/` の4ファイルと**実機の内容が一致していることを 2026-11-04 に確認済み**。

| リポジトリ | 実機 |
|---|---|
| `config/cxadc.rules` | `/etc/udev/rules.d/cxadc.rules` |
| `config/cxadc.conf` | `/etc/modprobe.d/cxadc.conf` |
| `config/gvusb2-modprobe.conf` | `/etc/modprobe.d/gvusb2.conf` |
| `config/gvusb2-modules-load.conf` | `/etc/modules-load.d/gvusb2.conf` |

### /etc/fstab の該当行

```
UUID=b6314394-4630-4073-a0f1-6015c0b9a8b8 /mnt/rf ext4 defaults,noatime,nofail 0 2
//192.168.128.120/home   /mnt/nas   cifs credentials=/etc/vhs-nas.cred,uid=1000,gid=1000,vers=3.0,iocharset=utf8,nofail,_netdev,x-systemd.automount 0 0
//192.168.128.120/rf_tmp /mnt/rftmp cifs credentials=/etc/vhs-nas.cred,uid=1000,gid=1000,vers=3.0,iocharset=utf8,nofail,_netdev,x-systemd.automount 0 0
```

**`/etc/vhs-nas.cred` の中身はここには置かない**（NASの認証情報）。
再構築時は `username=` / `password=` の2行を自分で書いて `chmod 600`。
`/etc/netplan/` も Wi-Fi の PSK が平文で入るため、同じ理由で除外している。

## DKMS

```
cxadc/0.1, 7.0.0-42-generic, x86_64: installed
```

## ソースの取得元とリビジョン（`~/src/`）

| ディレクトリ | リビジョン | 日付 | 取得元 |
|---|---|---|---|
| `cxadc-linux3` | `68b4ddb` | 2026-09-11 | https://github.com/happycube/cxadc-linux3.git |
| `vhs-decode` | `177b505` | 2026-10-06 | https://github.com/oyvindln/vhs-decode.git |
| `ld-decode` | `200b05d` | 2026-09-26 | https://github.com/happycube/ld-decode.git |
| `tbc-tools` | `932ba5a` | 2026-10-18 | https://github.com/harrypm/tbc-tools.git |
| `GV-USB2-Linux` | `d6f1818` | 2024-11-27 | https://github.com/harrypm/GV-USB2-Linux.git |

## tbc-tools をビルドするのに必要だった回避策

この3つが無いとビルドが通らない。

### 1. ONNX Runtime の Linux 版を自前で置く

リポジトリには Windows 版しか入っていない。

```
~/opt/onnxruntime/onnxruntime-linux-x64-1.18.1/
```

を用意して `-DONNXRUNTIME_ROOT=` で渡す。

### 2. `ld-lds-converter` を除外する

`flac >= 1.5.0` を要求するが Ubuntu 24.04 には無い。
LaserDisc の `.lds` 変換専用で、VHS 用途では他のどこからも参照されない。

```diff
--- CMakeLists.txt.orig
+++ CMakeLists.txt
@@ -375,7 +375,8 @@
 add_subdirectory(src/tbc-export-metadata)
 add_subdirectory(src/tbc-metadata-converter)
 add_subdirectory(src/audio-align)
-add_subdirectory(src/ld-lds-converter)
+# [local patch] flac>=1.5.0 が Ubuntu 24.04 に無いため除外。LaserDisc .lds 変換専用で他は依存しない
+#add_subdirectory(src/ld-lds-converter)
 add_subdirectory(src/tbc-process-vbi)
 add_subdirectory(src/ac3-decoder)
 add_subdirectory(src/library)
```

原本は `CMakeLists.txt.orig` として同じディレクトリに残してある。

### 3. Qt6 SVG のパッケージ名

`qt6-svg-dev`（`libqt6svg6-dev` ではない）。

### ビルドコマンド

```
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DONNXRUNTIME_ROOT=$HOME/opt/onnxruntime/onnxruntime-linux-x64-1.18.1
cmake --build build -j8
```

システムインストールはしていない。成果物は `~/src/tbc-tools/build/bin/` に置いたまま使う。

## 既知の罠: PATH 上の `tbc-video-export` が 0.1.8 のまま

```
$ which tbc-video-export
/home/taku/.local/bin/tbc-video-export
$ tbc-video-export --version
0.1.8
```

pip で入った 0.1.8 が `~/.local/bin` から先に引っかかり、ビルドした 3.3.0 を覆い隠す。
0.1.8 は補助ツールを旧名 `ld-dropout-correct` で探すため**必ず失敗する**。

**現状これが表面化していないのは、書き出し工程を Mac 側で回しているため。**
Ubuntu 側で書き出す場合は `~/src/tbc-tools/build/bin/` をフルパスで呼ぶか、
PATH の先頭に入れること。

`~/.local/bin` には他に `vhs-decode` / `hifi-decode` / `cvbs-decode` /
`decode.py` / `ld-decode` 等が入っている（こちらは正常に使っている）。

## 再構築の順序

1. Ubuntu 24.04 を入れる
2. `setup.sh` を流す
3. `config/` の4ファイルを配置して `udevadm control --reload`
4. `/etc/vhs-nas.cred` を手で書いて `chmod 600`、fstab にCIFSの2行を足す
5. `~/src/` の5リポジトリを上表のリビジョンで取得
6. ONNX Runtime を配置 → `CMakeLists.txt` を上のdiffで改変 → tbc-tools をビルド
7. `/mnt/rf` を作って ext4 で専用化

ゲインの最適値（`level=24` + `sixdb=1`、`vmux=2`）は実測で決めたもので、
`config/cxadc.rules` に入っている。**ここをやり直す必要は無い。**
