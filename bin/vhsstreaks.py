#!/usr/bin/env python3
"""
画素から VHS のドロップアウト（横縞）を数える。

RFキャプチャには vhs-decode がフィールドごとの dropOuts を残すが、昔の
ハードウェアMPEGキャプチャには何も残っていない。比較の相手にするには、
出来上がった映像から縞そのものを見つけるしかない。

縞の見え方
  ・横に長く伸びる（幅は数十〜数百画素）
  ・上下の行と明るさが大きく違う（たいてい明るい側へ跳ねる）
  ・インタレースなので、1つの縞は片方のフィールドにしか出ない

だから「行の平均が上下の行より突出していて、かつその行に明るい画素が
一定割合ある」行を数える。偶数行と奇数行を別に数えれば、2つの回転ヘッドの
どちらで読まれた縞かが分かる（どちらがAかは不明。vhsdropouts.py と同じ限界）。

しきい値は目で見て決める。--dump で候補のコマをPNGに落とせる。
"""
import argparse, subprocess, sys, os
import numpy as np

AP = argparse.ArgumentParser()
AP.add_argument("src")
AP.add_argument("--ss", type=float, default=0.0, help="開始秒")
AP.add_argument("--t", type=float, default=0.0, help="長さ秒（0で全部）")
AP.add_argument("--w", type=int, default=360, help="横の解像度（縦は落とさない）")
AP.add_argument("--h", type=int, default=480)
AP.add_argument("--excess", type=float, default=25.0, help="上下の行との明るさ差")
AP.add_argument("--frac", type=float, default=0.08, help="行内の明るい画素の割合")
AP.add_argument("--bright", type=int, default=200, help="明るいとみなす輝度")
# コマ速度は決め打ちにしない。納品物は bwdif=mode=send_field で59.94コマ/秒に
# 展開されるので、29.97を仮定すると出てくる時刻が全部2倍になる。実際に
# 2026-11-12 それで tape05 の乱れの時刻を倍に読み違えた。既定は None にして
# ffprobe から読む。
AP.add_argument("--fps", type=float, default=None,
                help="既定は入力から読む。指定したときだけ上書き")
AP.add_argument("--dump", default=None, help="上位の候補時刻をこのディレクトリにPNGで落とす")
AP.add_argument("--mtop", type=int, default=6,
                help="フィールド上端の除外行数（VBI・垂直帰線の残り）")
AP.add_argument("--mbot", type=int, default=14,
                help="フィールド下端の除外行数。VHSはここにヘッド切替ノイズが"
                     "必ず出る。正常な現象なのでドロップアウトと混ぜない")
AP.add_argument("--json", default=None)
A = AP.parse_args()

if A.fps is None:
    r = subprocess.run(["ffprobe","-v","error","-select_streams","v:0",
        "-show_entries","stream=avg_frame_rate,r_frame_rate","-of","csv=p=0", A.src],
        capture_output=True, text=True).stdout.strip().split(",")
    for tok in r:
        if "/" in tok:
            a, b = tok.split("/")
            if float(b) != 0 and float(a) != 0:
                A.fps = float(a)/float(b); break
    if A.fps is None:
        sys.exit("コマ速度を読めなかった。--fps で指定して")
    print(f"  コマ速度 {A.fps:.4f}/秒 （入力から読んだ）")

cmd = ["ffmpeg", "-nostdin", "-v", "error"]
if A.ss: cmd += ["-ss", str(A.ss)]
cmd += ["-i", A.src]
if A.t:  cmd += ["-t", str(A.t)]
cmd += ["-vf", f"scale={A.w}:{A.h}:flags=neighbor", "-pix_fmt", "gray",
        "-f", "rawvideo", "-"]
FSZ = A.w * A.h
p = subprocess.Popen(cmd, stdout=subprocess.PIPE)

# 上下の行との差を出すための畳み込み核。自分の行は含めず、±2行の平均を取る。
K = np.array([0.25, 0.25, 0.0, 0.25, 0.25])

per_frame = []          # (フィールドAの縞数, フィールドBの縞数)
row_hist  = np.zeros(A.h // 2, dtype=np.int64)
nfr = 0
buf = b""
while True:
    chunk = p.stdout.read(FSZ * 8)
    if not chunk:
        break
    buf += chunk
    n = len(buf) // FSZ
    for k in range(n):
        fr = np.frombuffer(buf[k*FSZ:(k+1)*FSZ], dtype=np.uint8).reshape(A.h, A.w)
        cnt = []
        for par in (0, 1):
            fld = fr[par::2].astype(np.float32)          # 片方のフィールド
            rm  = fld.mean(axis=1)
            base = np.convolve(rm, K, mode="same")
            # 端の2行は基準が足りないので除く
            excess = rm - base
            excess[:2] = 0; excess[-2:] = 0
            bf = (fld > A.bright).mean(axis=1)
            hit = (excess > A.excess) & (bf > A.frac)
            # 上下端を外す。下端はヘッド切替ノイズ、上端はVBIの残りで、
            # どちらもテープの傷とは関係なく毎コマ出る。
            hit[:A.mtop] = False
            if A.mbot: hit[-A.mbot:] = False
            cnt.append(int(hit.sum()))
            row_hist[: len(hit)] += hit
        per_frame.append((cnt[0], cnt[1]))
        nfr += 1
    buf = buf[n*FSZ:]
p.stdout.close(); p.wait()

PF = np.array(per_frame, dtype=np.int64)
if len(PF) == 0:
    sys.exit("1コマも読めなかった")
A0, B0 = int(PF[:,0].sum()), int(PF[:,1].sum())
dur = nfr / A.fps
print(f"入力 {A.src}")
print(f"  読んだコマ {nfr}  = {dur:.1f} 秒 ({dur/60:.1f} 分)   {A.w}x{A.h}")
print(f"  しきい値: 上下差 {A.excess} / 明画素割合 {A.frac} / 輝度 {A.bright}")
print()
print("=== 総量 ===")
print(f"  縞のあった行の総数  {A0+B0}")
print(f"  1000コマあたり      {(A0+B0)/nfr*1000:.1f}")
print(f"  縞のあったコマ      {int((PF.sum(axis=1)>0).sum())} / {nfr} "
      f"({(PF.sum(axis=1)>0).mean()*100:.1f}%)")
print()
print("=== フィールド別（＝回転ヘッド別。どちらがAかは不明）===")
print(f"  偶数行フィールド {A0:8d} ({A0/max(A0+B0,1)*100:5.1f}%)")
print(f"  奇数行フィールド {B0:8d} ({B0/max(A0+B0,1)*100:5.1f}%)")
if min(A0,B0) > 0:
    r = max(A0,B0)/min(A0,B0)
    print(f"  偏り {r:.2f} 倍", end="  ")
    print("→ ほぼ同じ。テープ側" if r < 1.3 else
          ("→ 中くらいの偏り" if r < 2.0 else "→ 強い偏り。片ヘッドの疑い"))

nb = max(1, int(dur/60))
step = nfr/nb
print()
print(f"=== 時間軸（{nb}分割、1000コマあたり）===")
prof=[]
for b in range(nb):
    lo, hi = int(b*step), int((b+1)*step)
    c = int(PF[lo:hi].sum()); d = c/max(1,hi-lo)*1000
    prof.append((A.ss+lo/A.fps, c, d))
mx = max((x[2] for x in prof), default=0)
for t, c, d in prof:
    bar = "#"*int(round(d/mx*40)) if mx else ""
    print(f"  {int(t)//60:3d}:{int(t)%60:02d}  {c:7d} {d:7.1f}  {bar}")

print()
print("=== 縞が多い秒 上位12 ===")
sec = {}
for i, (a, b) in enumerate(per_frame):
    if a+b:
        t = int(A.ss + i/A.fps); sec[t] = sec.get(t,0) + a+b
top = sorted(sec.items(), key=lambda kv:-kv[1])[:12]
for t, c in top:
    print(f"  {t//60:3d}:{t%60:02d}  {c:5d} 行")

print()
print("=== 縞の縦位置（フィールド内の行、上位10）===")
for i in np.argsort(-row_hist)[:10]:
    if row_hist[i]:
        print(f"  フィールド内 {int(i):3d} 行目: {int(row_hist[i]):7d} 件")

if A.dump and top:
    os.makedirs(A.dump, exist_ok=True)
    # 秒ではなく「縞が一番多かった正確なコマ」を落とす。秒で落とすと
    # 別のコマを見ることになって、検出器の確認にならない。
    order = np.argsort(-(PF.sum(axis=1)))
    for i in order[:5]:
        c = int(PF[i].sum())
        if c == 0: break
        ts = A.ss + int(i)/A.fps
        o = f"{A.dump}/f{int(i):07d}_{c}行_{ts:.2f}s.png"
        subprocess.run(["ffmpeg","-nostdin","-v","error","-y","-ss",f"{ts:.3f}",
                        "-i",A.src,"-frames:v","1","-vsync","0",o])
        print(f"  落とした {o}   （{int(ts)//60}:{int(ts)%60:02d} / {c}行）")

if A.json:
    import json
    json.dump({"source":os.path.abspath(A.src),"frames":nfr,"duration_sec":dur,
               "rows_total":A0+B0,"per_1000_frames":(A0+B0)/nfr*1000,
               "field_even":A0,"field_odd":B0,
               "profile":[{"start":t,"rows":c,"per_1000":d} for t,c,d in prof],
               "row_hist":[int(x) for x in row_hist],
               "thresholds":{"excess":A.excess,"frac":A.frac,"bright":A.bright},
               "version":1}, open(A.json,"w"), ensure_ascii=False)
    print(f"\n要約を書いた: {A.json}")
