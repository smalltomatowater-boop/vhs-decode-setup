set -u
# tape12 本番（TBC・映像はNAS、マスターとmp4はssd128g(BOT)に出して後でNASへ）
export VHS_NAS_DIR=/Volumes/rf_tmp
export VHS_WORK_DIR=/Volumes/rf_tmp
export VHS_VIDEO_DIR=/Volumes/rf_tmp/mac_tape12
export VHS_MKV_DIR=/Volumes/ssd128g/tape12_master
export VHS_MP4_DIR=/Volumes/ssd128g/tape12_mp4
export VHS_THREADS=4 VHS_NEED_PCT=200
echo "=== tape12 本番 開始 $(date +%H:%M:%S) ==="
for v in VHS_NAS_DIR VHS_WORK_DIR VHS_VIDEO_DIR VHS_MKV_DIR VHS_MP4_DIR VHS_THREADS; do eval "printf '  %-14s %s\n' $v \"\$$v\""; done
echo "--- 事前確認 ---"
ok=1
mkdir -p "$VHS_MKV_DIR" "$VHS_MP4_DIR"
for d in "$VHS_NAS_DIR" "$VHS_WORK_DIR" "$VHS_MKV_DIR" "$VHS_MP4_DIR"; do
  [ -d "$d" ] && echo "  ✓ $d" || { echo "  ✗ $d が無い"; ok=0; }
done
[ -f "$VHS_NAS_DIR/rf_tape12.u8" ] && echo "  ✓ RF $(du -h "$VHS_NAS_DIR/rf_tape12.u8" | cut -f1)" || { echo "  ✗ RFが無い"; ok=0; }
[ -f "$VHS_NAS_DIR/ref_tape12.mkv" ] && echo "  ✓ 参照 $(du -h "$VHS_NAS_DIR/ref_tape12.mkv" | cut -f1)" || { echo "  ✗ 参照が無い"; ok=0; }
av=$(df -k "$VHS_WORK_DIR" | tail -1 | awk '{print int($4/1048576)}')
echo "  NAS 空き ${av}GiB（TBC約100+映像約25で 130 要る）"
[ "$av" -ge 600 ] || { echo "  ✗ 空きが足りない"; ok=0; }
sv=$(df -k "$VHS_MKV_DIR" | tail -1 | awk '{print int($4/1048576)}')
echo "  ssd128g 空き ${sv}GiB（マスター約25+mp4約6で 35 要る）"
[ "$sv" -ge 50 ] || { echo "  ✗ ssd128g の空きが足りない"; ok=0; }
[ "$(networksetup -getairportpower en1 | grep -c Off)" = 1 ] && echo "  ✓ Wi-Fi Off" || { echo "  ✗ Wi-Fiが On"; ok=0; }
[ "$ok" = 1 ] || { echo "事前確認で止めた"; exit 1; }
mkdir -p "$VHS_VIDEO_DIR"
/Users/taku/vhs-decode-setup/bin/vhsfinish tape12
echo "=== おわり $(date +%H:%M:%S) ==="
