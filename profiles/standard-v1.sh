#!/bin/bash
# profile-standard-v1  （凍結日 2026-11-02）
#
# 保存マスター(FFV1・無加工・フルレンジ)から標準納品版を作るための固定値。
# このファイルは変更しない。設定を変えるときは standard-v2.sh を作って
# 別途検証する。毎回パラメータを触ると品質の再現性が無くなるため。
#
# 検証記録: docs/verify-standard-v1.md
#   3場面(黒シルエット・雪原 / 黒スーツ・白壁 / 暗い室内)で
#   構造損失 最大 0.0668%、符号化忠実度 SSIM 0.961〜0.974 / PSNR 41〜43.5dB。
#   ※これは当該3場面・当該検出条件での値であり、テープ全編の保証値ではない。

PROFILE_NAME="standard-v1"
PROFILE_LABEL="標準"

# --- 黒レベル ---
# 書き出しはフルレンジ(黒=0 白=1023)。68 は全編ヒストグラムの下位0.5%付近。
# 84 は黒い被写体のある場面で、潰れた画素の17〜26%が10画素以上の連続構造に
# なる（スーツの陰影・髪の束）ため、保存目的の標準には使わない。
# 107 は全編の9.6%を潰すので論外。
BLACK=68

# --- ノイズ処理 ---
# デッキ内蔵3DNRより大幅に弱い設定。細部の損失は実測 -2.5%。
# 黒レベル補正はノイズを 1023/(1023-BLACK) 倍に増幅するため、その相殺も兼ねる。
NR="hqdn3d=2:1:4:4"

# --- 映像 ---
# インタレース解除は send_field（59.94fps化）。VHSの動きの滑らかさを保つ。
# 切り出しは 760x488 の出力から有効画面 704x480 を取り、4:3 の 640x480 へ。
# フル→リミテッド変換をここで行う。大半のプレーヤーはタグを見ないため、
# 納品物は確実に表示される符号化にしておく。
DEINTERLACE="bwdif=mode=send_field:parity=tff"
CROP="crop=704:480:28:4"
SCALE="scale=640:480:flags=lanczos:in_range=pc:out_range=tv,setsar=1"

# --- 符号化 ---
VCODEC=(-c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p)
VTAGS=(-color_range tv -colorspace smpte170m -color_primaries smpte170m -color_trc smpte170m)
ACODEC=(-c:a aac -b:a 192k)
MUXOPT=(-movflags +faststart)

# v1 では tmcd(QuickTimeタイムコードトラック)がffmpegにより自動付与される。
# 除去は -write_tmcd 0 で可能だが、v1 の検証はこれを付けない状態で行ったため
# v1 には入れない。方針として納品にタイムコードは不要なので standard-v2 で
# 評価する。
