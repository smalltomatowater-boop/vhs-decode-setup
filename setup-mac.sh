#!/bin/bash
# Mac側（仕上げ機）の環境構築スクリプト
#
# Ubuntu機は収録とデコードを担い、書き出し以降はこの機で行う。
# 分担の理由: Ubuntu機の搭載メモリに不良があり、書き出し時に静かにビットを
# 壊す（同一ファイルの3回読みでCRC不一致の位置が毎回変わる。実際に
# tape01.mkv を19か所焼き付けて失った）。
#
#   ./setup-mac.sh            全部
#   ./setup-mac.sh tbc-tools  tbc-tools だけ
#   ./setup-mac.sh verify     いま入っているものの版を表示して検査
#
# 検証済みの構成（2026-11-02 / Apple M4 10コア 32GB / macOS 26.5.1）:
#   homebrew  cmake 4.2.3 / ninja 1.13.2 / fftw 3.3.10_3 / qt 6.10.2
#             ffmpeg 8.0.1_4 / flac 1.5.0 / mkvtoolnix 103.0 / pipx 1.8.0
#   python    /opt/homebrew/bin/python3 (3.14) + numpy 2.4.4
#   onnx      onnxruntime-osx-arm64-1.18.1
#   tbc-tools harrypm/tbc-tools @ a5692e3（tbc-video-export 3.3.0 を同梱）
#   vhs-decode oyvindln/vhs-decode @ 6cfd37b（pipx）
set -euo pipefail

SRC="$HOME/src"
OPT="$HOME/opt"
REPO="$(cd "$(dirname "$0")" && pwd)"
ONNX_VER=1.18.1
ONNX_ROOT="$OPT/onnxruntime/onnxruntime-osx-arm64-$ONNX_VER"
PY=/opt/homebrew/bin/python3

c()  { printf '\n\033[1;36m=== %s ===\033[0m\n' "$*"; }
ok() { printf '  \033[32m✓\033[0m %s\n' "$*"; }
ng() { printf '  \033[31m✗\033[0m %s\n' "$*"; }
wn() { printf '  \033[33m!\033[0m %s\n' "$*"; }

step_brew() {
  c "Homebrew の依存"
  command -v brew >/dev/null || { ng "Homebrew が無い。https://brew.sh から先に入れること"; exit 1; }
  # qt は tbc-analyse などGUIツールのビルドに要る。ffmpeg と mkvtoolnix は
  # 仕上げ工程そのもの（mkvpropedit でレンジタグを直す）。
  brew install cmake ninja fftw qt ffmpeg flac mkvtoolnix pipx python
  ok "導入完了"

  # Homebrew の ffmpeg は libsoxr を含まない。aresample の resampler=soxr は
  # 「Requested resampling engine is unavailable」で落ちるので、仕上げ側は
  # 標準の swr を filter_size=128 で使っている。ここは直せないので記録だけ。
  if ffmpeg -hide_banner -version | grep -q libsoxr; then
    ok "ffmpeg は libsoxr あり"
  else
    wn "ffmpeg に libsoxr が無い（vhsfinish は標準swrを使うので問題ない）"
  fi
}

step_python() {
  c "Python と numpy"
  [ -x "$PY" ] || { ng "$PY が無い。brew install python を先に"; exit 1; }
  if "$PY" -c 'import numpy' 2>/dev/null; then
    ok "numpy $("$PY" -c 'import numpy;print(numpy.__version__)')"
  else
    # Homebrew の python は外部管理扱いなので --break-system-packages が要る。
    # numpy は vhsalign.py（相互相関）と vhsqa.py（測定）で使う。
    "$PY" -m pip install --break-system-packages numpy
    ok "numpy $("$PY" -c 'import numpy;print(numpy.__version__)')"
  fi
}

step_onnx() {
  c "ONNX Runtime （tbc-tools のビルドに必要）"
  # tbc-tools に同梱されているのは Windows 版のみ。arm64 Mac 用は別途要る。
  if [ -f "$ONNX_ROOT/include/onnxruntime_cxx_api.h" ]; then ok "導入済み $ONNX_ROOT"; return; fi
  mkdir -p "$OPT/onnxruntime" && cd "$OPT/onnxruntime"
  curl -fsSL -o ort.tgz \
    "https://github.com/microsoft/onnxruntime/releases/download/v${ONNX_VER}/onnxruntime-osx-arm64-${ONNX_VER}.tgz"
  tar xzf ort.tgz && rm -f ort.tgz
  ok "$ONNX_ROOT"
}

step_vhsdecode() {
  c "vhs-decode"
  mkdir -p "$SRC" && cd "$SRC"
  [ -d vhs-decode ] || git clone https://github.com/oyvindln/vhs-decode.git
  cd vhs-decode
  pipx install . --force
  ok "$(command -v vhs-decode) @ $(git log --oneline -1)"
}

step_tbctools() {
  c "tbc-tools （カラー復号・ドロップアウト補正・書き出し）"
  step_onnx
  mkdir -p "$SRC" && cd "$SRC"
  [ -d tbc-tools ] || git clone --recurse-submodules https://github.com/harrypm/tbc-tools.git
  cd tbc-tools

  # Linux側で要ったCMakeLists.txtのパッチ（flac>=1.5.0が無くて
  # ld-lds-converter を外す）は Mac では不要。Homebrew に flac 1.5.0 がある。
  cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_PREFIX_PATH=/opt/homebrew/opt/qt \
    -DONNXRUNTIME_ROOT="$ONNX_ROOT"
  cmake --build build -j"$(sysctl -n hw.physicalcpu)"
  ok "$(ls build/bin | wc -l | tr -d ' ') 個のツールをビルド → $PWD/build/bin"
}

step_tools() {
  c "仕上げ用スクリプトの配置"
  mkdir -p "$HOME/bin"
  # コピーではなくシンボリックリンクにする。vhsfinish は profiles/ を
  # リポジトリ本体からの相対で読むため、コピーだとプロファイルを見失う。
  # リンクは自分で辿って実体の位置を出すようにしてある。
  # git pull するだけで中身が新しくなる利点もある。
  for f in vhsfinish vhsclean vhsdeliver vhsverify vhsalign.py vhsqa.py; do
    ln -sf "$REPO/bin/$f" "$HOME/bin/$f"
  done
  ok "$HOME/bin/ に6本リンク（実体は $REPO/bin/）"

  case ":$PATH:" in
    *":$HOME/bin:"*) ok "~/bin は PATH に入っている" ;;
    *) wn "~/bin が PATH に無い。~/.zshrc に書くこと" ;;
  esac
}

step_nas() {
  c "NAS のマウント"
  local NAS="${VHS_NAS_DIR:-/Volumes/home/VHS_RF}"
  if [ -d "$NAS" ]; then
    ok "$NAS （空き $(df -h "$NAS" | awk 'NR==2{print $4}')）"
  else
    ng "$NAS が見えない"
    echo "    Finder → 移動 → サーバへ接続 → smb://192.168.128.120/home"
    echo "    中間ファイルは内蔵SSDに置けない（30分テープのTBCで110GB）。"
    echo "    NASに直接置く。1000baseT全二重なので読みと書きは競合しない。"
  fi
}

step_verify() {
  c "いま入っているものの確認"
  local NG=0
  chk() { # chk 表示名 コマンド
    if out=$(eval "$2" 2>/dev/null) && [ -n "$out" ]; then printf '  \033[32m✓\033[0m %-20s %s\n' "$1" "$out"
    else printf '  \033[31m✗\033[0m %-20s 見つからない\n' "$1"; NG=$((NG+1)); fi
  }
  chk ffmpeg      "ffmpeg -hide_banner -version | head -1 | cut -d' ' -f1-3"
  chk ffprobe     "command -v ffprobe"
  chk mkvpropedit "mkvpropedit --version | head -1"
  chk vhs-decode  "command -v vhs-decode"
  chk tbc-export  "$SRC/tbc-tools/build/bin/tbc-video-export --version"
  chk python      "$PY -c 'import platform;print(platform.python_version())'"
  chk numpy       "$PY -c 'import numpy;print(numpy.__version__)'"
  chk onnx        "ls -d $ONNX_ROOT"

  # 古い tbc-video-export 0.1.8 が ~/.local/bin に残っていると、PATH順によって
  # こちらが先に見つかり、旧名 ld-dropout-correct を探して必ず失敗する。
  if [ -x "$HOME/.local/bin/tbc-video-export" ]; then
    local v; v=$("$HOME/.local/bin/tbc-video-export" --version 2>&1 | head -1)
    case "$v" in
      0.*) wn "~/.local/bin に古い $v がある。PATHで $SRC/tbc-tools/build/bin を先に置くこと" ;;
      *)   ok "~/.local/bin 側も $v" ;;
    esac
  fi

  echo
  [ "$NG" = 0 ] && ok "すべて揃っている" || ng "$NG 個足りない"
  return 0
}

case "${1:-all}" in
  brew)       step_brew ;;
  python)     step_python ;;
  onnx)       step_onnx ;;
  vhs-decode) step_vhsdecode ;;
  tbc-tools)  step_tbctools ;;
  tools)      step_tools ;;
  nas)        step_nas ;;
  verify)     step_verify ;;
  all)
    step_brew; step_python; step_vhsdecode; step_tbctools; step_tools; step_nas
    step_verify
    c "完了"
    echo "  使い方:  vhsfinish <名前>        NAS上のRFから納品物まで"
    echo "           vhsfinish <名前> --status  進捗だけ"
    ;;
  *) sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
