#!/bin/bash
# ssd128g -> NAS。1本ずつ、.partに書いて、サイズとmd5が合ったときだけ正式名にする。
NAS=taku@192.168.128.120
copy1(){ # src dst_dir_mac dst_dir_nas name
  local src="$1" dm="$2" dn="$3" name="$4"
  echo "=== $name  $(date +%T) ==="
  local sz=$(stat -f %z "$src")
  local sm=$(cat "$src" | tee "$dm/$name.part" | md5 -q)   # 読むのは1回
  echo "  コピー完了 $(date +%T)  元md5 $sm"
  local dsz=$(stat -f %z "$dm/$name.part")
  [ "$sz" = "$dsz" ] || { echo "✗ サイズ不一致 $sz vs $dsz"; return 1; }
  local sn=$(ssh -o BatchMode=yes $NAS "md5sum '$dn/$name.part'" | awk '{print $1}')
  echo "  NAS側md5 $sn  $(date +%T)"
  [ "$sm" = "$sn" ] || { echo "✗ md5不一致"; return 1; }
  mv -f "$dm/$name.part" "$dm/$name" && echo "  ✓ 照合OK → $name"
}
copy1 /Volumes/ssd128g/tape12_master/完成_tape12.mkv /Volumes/rf_mkv /volume1/rf_mkv 完成_tape12.mkv || exit 1
copy1 /Volumes/ssd128g/tape12_mp4/tape12_標準.mp4 /Volumes/rf_mp4 /volume1/rf_mp4 tape12_標準.mp4 || exit 1
copy1 /Volumes/ssd128g/tape12_mp4/tape12_コントラスト重視.mp4 /Volumes/rf_mp4 /volume1/rf_mp4 tape12_コントラスト重視.mp4 || exit 1
echo "=== おわり $(date +%T) ==="
