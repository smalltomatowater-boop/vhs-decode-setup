#!/usr/bin/env python3
"""
白飛び場面で vhs-decode が出す虹色ノイズを、コマ単位で見つける。

なぜ要るか
----------
2026-11-12、マスターが tape05（FANATIC◇CRISIS Truth）の納品物に乱れを
見つけた。調べると、原因はテープの傷でもデッキでもなく、**うちのRF経路**
だった。白飛びするフラッシュ場面で、デッキのS端子出力はきれいな白のまま
なのに、vhs-decode は色を増幅して虹色のゴミを出す。デッキには色が無い
ときに色を切る回路（カラーキラー）があり、vhs-decode には無い。

--chroma-decoder を ntsc3d から ntsc2d に変えても結果は同一だったので、
色の復号段ではなく、その手前のRFからの色の取り出し段の問題。

何を測るか
----------
2つ測って、両方を満たすコマだけを候補にする。

  いろどり   色差(U,V)の標準偏差。色が派手なほど大きい
  ざらつき   横に隣り合う画素の色差の差。虹色ノイズは隣とまったく違う色に
             なるので大きい。本当に色鮮やかな場面は色が滑らかなので小さい

「いろどり」だけで切ると、鮮やかな映像を巻き添えにする。「ざらつき」を
併用すると、ノイズだけを選べる。

縮小には flags=neighbor を使う。平均で縮めると高い周波数のノイズが
ならされて消えてしまい、探したいものが見えなくなる。

使い方
------
  vhschroma.py <動画> --scan                分布を見る（しきい値決め用）
  vhschroma.py <動画> --out ranges.json     色を切る区間を書き出す
"""
import argparse, json, os, subprocess, sys
import numpy as np

AP = argparse.ArgumentParser()
AP.add_argument("src")
AP.add_argument("--w", type=int, default=360)
AP.add_argument("--h", type=int, default=240)
AP.add_argument("--scan", action="store_true", help="分布だけ出して終わる")
# しきい値は tape05r で実測して決めた（2026-11-12）。既知の異常10コマと
# 正常10コマを 360x240 / flags=neighbor で測った結果:
#            いろどり        ざらつき
#   異常   24.4 〜 55.0     2.6 〜 10.0
#   正常    3.5 〜  8.9     0.7 〜  0.9
# どちらも約3倍の谷が空く。その谷の中に置く。解像度や縮小方法を変えると
# 目盛りが変わるので、既定の --w/--h/neighbor から外れるなら測り直すこと。
AP.add_argument("--sat", type=float, default=15.0, help="いろどりのしきい値")
AP.add_argument("--rough", type=float, default=1.6, help="ざらつきのしきい値")
AP.add_argument("--margin", type=float, default=0.15, help="前後に伸ばす秒")
AP.add_argument("--out", default=None)
A = AP.parse_args()

p = subprocess.run(["ffprobe","-v","error","-select_streams","v:0",
    "-show_entries","stream=avg_frame_rate","-of","csv=p=0", A.src],
    capture_output=True, text=True).stdout.strip()
num, den = p.split("/"); FPS = float(num)/float(den)
print(f"入力 {A.src}\n  コマ速度 {FPS:.4f}/秒")

cmd = ["ffmpeg","-nostdin","-v","error","-i",A.src,
       "-vf",f"scale={A.w}:{A.h}:flags=neighbor","-pix_fmt","yuv444p",
       "-f","rawvideo","-"]
P = subprocess.Popen(cmd, stdout=subprocess.PIPE)
N = A.w*A.h; FSZ = N*3
sat=[]; rough=[]; luma=[]
buf=b""
while True:
    c = P.stdout.read(FSZ*8)
    if not c: break
    buf += c
    n = len(buf)//FSZ
    for k in range(n):
        f = buf[k*FSZ:(k+1)*FSZ]
        y = np.frombuffer(f[:N], dtype=np.uint8).astype(np.int16)
        u = np.frombuffer(f[N:2*N], dtype=np.uint8).astype(np.int16).reshape(A.h,A.w)
        v = np.frombuffer(f[2*N:], dtype=np.uint8).astype(np.int16).reshape(A.h,A.w)
        sat.append((u.std()+v.std())/2)
        rough.append((np.abs(np.diff(u,axis=1)).mean()+np.abs(np.diff(v,axis=1)).mean())/2)
        luma.append(y.mean())
    buf = buf[n*FSZ:]
P.stdout.close(); P.wait()

S = np.array(sat); R = np.array(rough); L = np.array(luma)
T = np.arange(len(S))/FPS
print(f"  {len(S)} コマ = {len(S)/FPS:.1f} 秒\n")

def pct(a, name):
    q = np.percentile(a, [50,90,95,99,99.5,99.9,100])
    print(f"  {name:8s} 中央値 {q[0]:6.2f} | 90% {q[1]:6.2f} | 95% {q[2]:6.2f} | "
          f"99% {q[3]:6.2f} | 99.9% {q[5]:6.2f} | 最大 {q[6]:6.2f}")
print("=== 分布 ===")
pct(S,"いろどり"); pct(R,"ざらつき"); pct(L,"輝度")

if A.scan:
    print("\n=== いろどり上位20コマ ===")
    print("    時刻    いろどり  ざらつき   輝度")
    for i in np.argsort(-S)[:20]:
        print(f"  {int(T[i])//60}:{T[i]%60:06.3f} {S[i]:8.2f} {R[i]:9.2f} {L[i]:7.1f}")
    print("\n=== ざらつき上位20コマ ===")
    print("    時刻    いろどり  ざらつき   輝度")
    for i in np.argsort(-R)[:20]:
        print(f"  {int(T[i])//60}:{T[i]%60:06.3f} {S[i]:8.2f} {R[i]:9.2f} {L[i]:7.1f}")
    print("\n=== しきい値を変えたときに何コマ当たるか ===")
    print("   いろどり ざらつき   当たるコマ   全体に占める割合")
    for s in (10,12,14,16,20):
        for r in (6,8,9,12):
            m = (S>s)&(R>r)
            print(f"   {s:6.0f} {r:8.0f} {int(m.sum()):10d} "
                  f"{m.mean()*100:14.3f}%")
    sys.exit(0)

hit = (S > A.sat) & (R > A.rough)
idx = np.flatnonzero(hit)
runs = []
if len(idx):
    s = idx[0]; prev = idx[0]
    for i in idx[1:]:
        if i - prev > int(FPS*0.5):
            runs.append((s, prev)); s = i
        prev = i
    runs.append((s, prev))
out = [{"start": max(0.0, a/FPS - A.margin), "end": b/FPS + 1/FPS + A.margin,
        "frames": int(b-a+1), "sat_max": float(S[a:b+1].max()),
        "rough_max": float(R[a:b+1].max())} for a, b in runs]
print(f"\n=== 色を切る区間 {len(out)} 件 "
      f"（計 {sum(o['end']-o['start'] for o in out):.2f} 秒 / "
      f"{len(S)/FPS:.1f} 秒中 {sum(o['end']-o['start'] for o in out)/(len(S)/FPS)*100:.2f}%）===")
for o in out:
    print(f"  {int(o['start'])//60}:{o['start']%60:06.3f} 〜 "
          f"{int(o['end'])//60}:{o['end']%60:06.3f}  "
          f"{o['frames']:4d}コマ  いろどり{o['sat_max']:6.1f} ざらつき{o['rough_max']:6.1f}")
expr = "+".join(f"between(t,{o['start']:.3f},{o['end']:.3f})" for o in out)
res = {"source": os.path.abspath(A.src), "fps": FPS, "frames": len(S),
       "sat_threshold": A.sat, "rough_threshold": A.rough, "margin": A.margin,
       "ranges": out, "enable": expr or "0", "version": 1}
if A.out:
    with open(A.out, "w") as f: json.dump(res, f, ensure_ascii=False, indent=1)
    print(f"\n書いた: {A.out}")
