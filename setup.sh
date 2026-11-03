#!/bin/bash
# vhs-decode 環境の構築スクリプト（Ubuntu 24.04 / カーネル 6.10以降 想定）
#
# 何をするか:
#   1. cxadc （RFキャプチャドライバ）を DKMS で導入
#   2. vhs-decode 本体を pipx で導入（Rust は rustup で新しいものを使う）
#   3. tbc-tools（カラー復号・ドロップアウト補正）をビルド
#   4. GV-USB2 ドライバをパッチ当ててビルド
#   5. 設定ファイルと vhstool を配置
#
# 各ステップは独立しているので、引数で個別に実行できる:
#   ./setup.sh            全部
#   ./setup.sh cxadc      cxadc だけ
#   ./setup.sh tbc-tools  tbc-tools だけ
set -euo pipefail

SRC="$HOME/src"
OPT="$HOME/opt"
REPO="$(cd "$(dirname "$0")" && pwd)"
ONNX_VER=1.18.1
WORK=/mnt/rf

c()  { printf '\n\033[1;36m=== %s ===\033[0m\n' "$*"; }
ok() { printf '  \033[32m✓\033[0m %s\n' "$*"; }
ng() { printf '  \033[31m✗\033[0m %s\n' "$*"; }

need_root_hint() {
  printf '  \033[33msudo のパスワードを聞かれます\033[0m\n'
}

step_deps() {
  c "依存パッケージ"
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    build-essential dkms git pv pkg-config make cmake ninja-build curl \
    linux-headers-"$(uname -r)" \
    qtbase5-dev libqwt-qt5-dev libfftw3-dev \
    libavformat-dev libavcodec-dev libavutil-dev ffmpeg sox \
    qt6-base-dev qt6-tools-dev qt6-tools-dev-tools qt6-svg-dev \
    libxkbcommon-dev libxkbcommon-x11-dev libsqlite3-dev libgl1-mesa-dev \
    pipx g++ python3-dev python3-pip python3-numpy \
    flac v4l-utils bc
  ok "導入完了"
}

step_cxadc() {
  c "cxadc （RFキャプチャドライバ）"
  mkdir -p "$SRC" && cd "$SRC"
  [ -d cxadc-linux3 ] || git clone --depth 1 https://github.com/happycube/cxadc-linux3.git
  cd cxadc-linux3

  sudo rm -rf /usr/src/cxadc-0.1
  sudo cp -r . /usr/src/cxadc-0.1
  sudo dkms install -m cxadc -v 0.1 --force
  ok "DKMS 登録完了（カーネル更新時に自動リビルドされる）"

  # 設定ファイル。vmux/level/sixdb はモジュールパラメータではないので udev で設定する
  sudo cp "$REPO/config/cxadc.conf"  /etc/modprobe.d/cxadc.conf
  sudo cp "$REPO/config/cxadc.rules" /etc/udev/rules.d/cxadc.rules
  echo cxadc | sudo tee /etc/modules-load.d/cxadc.conf >/dev/null
  sudo udevadm control --reload-rules

  # 競合する純正ドライバを退けて載せ替え
  for m in cx88_alsa cx8800 cx88_blackbird cx8802 cx2341x cx88xx; do
    sudo modprobe -r "$m" 2>/dev/null || true
  done
  sudo modprobe -r cxadc 2>/dev/null || true
  sudo modprobe cxadc
  sleep 2
  sudo udevadm settle

  [ -c /dev/cxadc0 ] && ok "/dev/cxadc0 を確認" || { ng "/dev/cxadc0 が出ない"; return 1; }
  sudo usermod -aG video "$USER"
  ok "$USER を video グループに追加（反映には再ログインが必要）"
}

step_storage() {
  c "収録先 $WORK"
  if mountpoint -q "$WORK"; then
    ok "マウント済み（$(df -h "$WORK" | awk 'NR==2{print $4}') 空き）"
  else
    ng "$WORK が無い。専用パーティションを ext4 で用意して fstab に書くこと"
    cat <<'EOS'
    例（/dev/sdX を丸ごと使う場合。中身は消える）:
      sudo wipefs -a /dev/sdX
      sudo sgdisk --zap-all /dev/sdX && sudo sgdisk -n 1:0:0 -t 1:8300 /dev/sdX
      sudo mkfs.ext4 -L RFCAP -m 1 -E lazy_itable_init=0,lazy_journal_init=0 /dev/sdX1
      sudo mkdir -p /mnt/rf
      echo "UUID=$(sudo blkid -s UUID -o value /dev/sdX1) /mnt/rf ext4 defaults,noatime,nofail 0 2" | sudo tee -a /etc/fstab
      sudo mount /mnt/rf && sudo chown "$USER:$USER" /mnt/rf
EOS
  fi
}

step_rust() {
  c "Rust ツールチェーン"
  # Ubuntu 24.04 の cargo 1.75 では vhs-decode の Cargo.lock (v4) を読めない
  if command -v rustc >/dev/null && [ "$(rustc --version | cut -d' ' -f2 | cut -d. -f2)" -ge 78 ]; then
    ok "$(rustc --version)"
    return
  fi
  sudo apt-get remove -y rustc cargo 2>/dev/null || true
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y rustup
  rustup default stable
  ok "$(rustc --version)"
}

step_vhsdecode() {
  c "vhs-decode"
  mkdir -p "$SRC" && cd "$SRC"
  [ -d vhs-decode ] || git clone --depth 1 https://github.com/oyvindln/vhs-decode.git
  export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
  pipx ensurepath >/dev/null 2>&1 || true
  pipx install tbc-video-export 2>/dev/null || pipx upgrade tbc-video-export || true
  cd vhs-decode
  pipx install . --force
  ok "$(command -v vhs-decode)"
}

step_onnx() {
  c "ONNX Runtime (tbc-tools のビルドに必要)"
  # tbc-tools に同梱されているのは Windows 版のみで、Linux では別途用意が要る
  local root="$OPT/onnxruntime/onnxruntime-linux-x64-$ONNX_VER"
  if [ -f "$root/include/onnxruntime_cxx_api.h" ]; then ok "導入済み"; echo "$root"; return; fi
  mkdir -p "$OPT/onnxruntime" && cd "$OPT/onnxruntime"
  curl -fsSL -o ort.tgz \
    "https://github.com/microsoft/onnxruntime/releases/download/v${ONNX_VER}/onnxruntime-linux-x64-${ONNX_VER}.tgz"
  tar xzf ort.tgz && rm -f ort.tgz
  ok "$root"
}

step_tbctools() {
  c "tbc-tools （カラー復号・ドロップアウト補正）"
  step_onnx >/dev/null
  local root="$OPT/onnxruntime/onnxruntime-linux-x64-$ONNX_VER"
  mkdir -p "$SRC" && cd "$SRC"
  [ -d tbc-tools ] || git clone --depth 1 --recurse-submodules --shallow-submodules \
      https://github.com/harrypm/tbc-tools.git
  cd tbc-tools

  # flac>=1.5.0 は Ubuntu 24.04 に無い。要求しているのは LaserDisc 専用の
  # ld-lds-converter だけで他は依存していないので構成から外す
  if grep -qE '^add_subdirectory\(src/ld-lds-converter\)' CMakeLists.txt; then
    cp -n CMakeLists.txt CMakeLists.txt.orig
    patch -p0 --forward < "$REPO/patches/tbc-tools-01-skip-ld-lds-converter.patch" || true
  fi

  cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DONNXRUNTIME_ROOT="$root"
  cmake --build build -j"$(nproc)"
  ok "$(ls build/bin | wc -l) 個のツールをビルド → $PWD/build/bin"
  echo "    PATH に通すか sudo cmake --install build で導入する"
}

step_gvusb2() {
  c "GV-USB2 ドライバ"
  mkdir -p "$SRC" && cd "$SRC"
  [ -d GV-USB2-Driver ] || git clone --depth 1 https://github.com/Isaac-Lozano/GV-USB2-Driver.git
  cd GV-USB2-Driver

  # (a) Linux 6.10 以降 vb2_ops から wait_prepare/wait_finish が削除された
  grep -q 'wait_prepare' gvusb2-v4l2.c && {
    cp -n gvusb2-v4l2.c gvusb2-v4l2.c.orig
    patch -p0 --forward < "$REPO/patches/gvusb2-01-vb2-wait-callbacks.patch" || true
  }
  # (b) EHCI + 4GB超メモリ + IOMMU無し では swiotlb の 256KB 上限に引っかかる
  grep -q 'GVUSB2_NUM_ISOCH_PACKETS 0x100' gvusb2.h && {
    cp -n gvusb2.h gvusb2.h.orig
    patch -p0 --forward < "$REPO/patches/gvusb2-02-swiotlb-urb-size.patch" || true
  }

  make clean >/dev/null 2>&1 || true
  make
  local K; K=$(uname -r)
  sudo mkdir -p "/lib/modules/$K/extra"
  sudo cp gvusb2-sound.ko gvusb2-video.ko "/lib/modules/$K/extra/"
  sudo depmod -a
  sudo cp "$REPO/config/gvusb2-modprobe.conf"     /etc/modprobe.d/gvusb2.conf
  sudo cp "$REPO/config/gvusb2-modules-load.conf" /etc/modules-load.d/gvusb2.conf
  ok "導入完了（反映は再起動が確実）"
}

step_tools() {
  c "vhstool"
  mkdir -p "$HOME/bin"
  cp "$REPO/bin/vhstool" "$REPO/bin/vhsalign.py" "$REPO/bin/vhslevel.py" "$HOME/bin/"
  chmod +x "$HOME/bin/vhstool" "$HOME/bin/vhsalign.py" "$HOME/bin/vhslevel.py"
  ok "$HOME/bin/ に配置（~/.profile が ~/bin を PATH に入れる）"
}

case "${1:-all}" in
  deps)       step_deps ;;
  cxadc)      step_cxadc ;;
  storage)    step_storage ;;
  rust)       step_rust ;;
  vhs-decode) step_vhsdecode ;;
  onnx)       step_onnx ;;
  tbc-tools)  step_tbctools ;;
  gvusb2)     step_gvusb2 ;;
  tools)      step_tools ;;
  all)
    need_root_hint
    step_deps; step_cxadc; step_storage; step_rust
    step_vhsdecode; step_tbctools; step_gvusb2; step_tools
    c "完了"
    echo "  再起動してから  vhstool check  で確認すること"
    ;;
  *) sed -n '2,15p' "$0"; exit 1 ;;
esac
