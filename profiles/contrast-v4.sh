#!/bin/bash
# profile-contrast-v4  （2026-11-13）
#
# ★ 0 IRE マスター専用。7.5 IRE 時代のマスターには使えない。
#   vhsdeliver が mkv の VHS_BLACK_IRE タグと突き合わせて止める。
#
# contrast-v2 からの変更は黒点だけ。切り出し・ノイズ処理・符号化は同一。
#
# --- なぜ 137 か -----------------------------------------------------
# マスターの黒レベルを 0 IRE に直したことで、書き出し後の値が
#   out_new = 0.9431 × out_old + 58.24
# だけずれた（信号全体の一次変換。詳細は docs/verify-ntscj-0ire.md）。
# v2 の BLACK=84 をこの式に通すと 137.5 になる。
#
# つまり **見た目は contrast-v2 と同じ**。これまで納品した6本と並べても
# 違和感が出ない。変わるのは色が 6.0% 薄くなること（v2 までが
# 濃すぎた。同じ 0.9431 倍が色差にもかかっていた）と、
# 暗部の情報がマスター側に残っていること。
#
# 実測（tape05 全編）: 潰れる画素は v2 が 17.19%、このプロファイルが 17.37%。
# ほぼ同じ。見栄えの設計はそのまま引き継いでいる。
#
# 情報を捨てたくない顧客には standard-v4（BLACK=4）を渡すこと。
# ----------------------------------------------------------------------
PROFILE_NAME="contrast-v4"
# 2026-11-13 新設。0 IRE マスター用。contrast-v2 と同じ見た目。
PROFILE_LABEL="コントラスト重視"

# --- 黒レベル ---
# 見栄え重視。contrast-v2 の 84 を 0 IRE 目盛りに載せ替えた値。
# 情報保持より見栄えを選ぶ顧客向け。
MASTER_BLACK_IRE=0
BLACK=137

# --- ノイズ処理 ---（v1 と同じ）
NR="hqdn3d=2:1:4:4"

# --- 映像 ---
# インタレース解除は send_field（59.94fps化）。VHSの動きの滑らかさを保つ。
# 切り出しは 760x488 の出力から有効走査 746x480 を取り、4:3 の 640x480 へ。
# フル→リミテッド変換をここで行う。大半のプレーヤーはタグを見ないため、
# 納品物は確実に表示される符号化にしておく。
DEINTERLACE="bwdif=mode=send_field:parity=tff"
CROP="crop=746:480:4:4"
SCALE="scale=640:480:flags=lanczos:in_range=pc:out_range=tv,setsar=1"

# --- 符号化 ---（v1 と同じ。MUXOPT にのみ -write_tmcd 0 を追加）
VCODEC=(-c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p)
VTAGS=(-color_range tv -colorspace smpte170m -color_primaries smpte170m -color_trc smpte170m)
ACODEC=(-c:a aac -b:a 192k)
# --- (2) tmcd ---
# マスターが TAG:TIMECODE=00:00:00:00 を持つため、ffmpeg が mp4 に
# データトラック tmcd を自動で足していた。納品にタイムコードは不要。
# 画素には一切影響しない。
MUXOPT=(-movflags +faststart -write_tmcd 0)
