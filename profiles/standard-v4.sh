#!/bin/bash
# profile-standard-v4  （2026-11-13）
#
# ★ 0 IRE マスター専用。7.5 IRE 時代のマスターには使えない。
#   vhsdeliver が mkv の VHS_BLACK_IRE タグと突き合わせて止める。
#
# standard-v2 からの変更は黒点だけ。切り出し・ノイズ処理・符号化は同一。
#
# --- なぜ黒点が変わるか ---------------------------------------------
# v2 までのマスターは --NTSCJ を付けずにデコードしていたため、米国式の
# 7.5 IRE セットアップが前提になっていた。日本のテープの黒は 0 IRE なので、
# 0〜7.5 IRE の帯が書き出しの時点で切り捨てられていた。
# 詳細は docs/verify-ntscj-0ire.md。
#
# 0 IRE のマスターでは、書き出し後の値 4 がそのまま 0 IRE ＝ 真の黒である。
# つまり BLACK=4 は「テープにあったものを一切捨てない」設定で、
# 0 IRE → 映像の黒(16)、100 IRE → 白(235) という素直な変換になる。
#
# 実測（tape05、全編685コマ 0.25G画素、等倍）:
#   床(値4)に張り付いた画素  7.5IREマスター 14.61% / 0IREマスター 11.45%
#   真っ黒リードイン20コマ    7.5IRE は 100% 床に張り付く（ノイズの粒まで
#   潰れている）。0IRE は 89.8%、99%点が値14 ＝ 粒が信号として残る
#
# v2 の BLACK=68 は、潰れた画素を床のぶんも含めて 16.67% にしていた。
# BLACK=4 では 11.45%、つまりマスターが持っている情報は全部通る。
#
# 見た目は v2 より明るく、コントラストは浅くなる。暗部のノイズも見える。
# 「見栄え」が欲しい顧客には contrast-v4 を渡すこと。
# ----------------------------------------------------------------------
PROFILE_NAME="standard-v4"
# 2026-11-13 新設。0 IRE マスター用。
PROFILE_LABEL="標準"

# --- 黒レベル ---
# 37 = 0.0 IRE ＝ 映像の黒そのもの。絵を見て決めた値ではなく、
# デコードが書き残した3つの数字から逆算した位置である。
#
#   blanking16bIre 15360.0   本物の 0 IRE（level_adjust がかからない）
#   black16bIre    16243.2 = (15360 + 7.5*358.4) * (1 - 0.1)
#   white16bIre    56320.0 = (15360 + 100*358.4) * (1 + 0.1)
#     → 1 IRE = 358.4、level_adjust = 0.1
#
# 書き出しは black16bIre→0、white16bIre→1023 に写す。--NTSCJ では
# black16bIre = 15360*0.9 = 13824 なので、目盛りはこうなる:
#
#     値  37 =   0.0 IRE   映像の黒 ← ここ
#     値 102 =   7.5 IRE   米国式セットアップ
#     値 122 =   9.9 IRE   standard-v2 の黒点68 と同じ見た目
#     値 137 =  11.6 IRE   contrast-v2 の黒点84 と同じ見た目
#     値 900 = 100.0 IRE   白（実測の最大 894 と一致）
#
# standard-v2 は黒より 9.9 IRE 上まで切り捨てていた。
# このプロファイルは 0 IRE より上を一切捨てない。
MASTER_BLACK_IRE=0
BLACK=37

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
