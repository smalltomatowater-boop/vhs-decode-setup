#!/usr/bin/env python3
"""
水平同期を失って横に裂けたコマを見つける。

なぜ要るか
----------
2026-11-12、マスターが tape05 の納品物の乱れを「すごいノイズ」と言った。
色ノイズ（bin/vhschroma.py が消す方）だけだと思っていたが、絵そのものが
横に裂けていた。本来は画面の外にある帰線期間が画面の中に出てきて、
黒い帯になり、その左右で絵がずれる。白飛びするフラッシュ場面で起きる。

色を抜いてもこれは直らない。「虹色に裂けた絵」が「モノクロで裂けた絵」に
なるだけ。裂けたコマは捨てて、直前のコマを保持するのが正しい。
1/60秒の静止は人の目にほぼ見えないが、黒い帯は必ず見える。

tape05r での実測:
   正常なコマ                     黒い列 0本
   100s 102s 103s 192s 245s 398s  黒い列が画面幅の 5.9〜21.5%

検証（2026-11-12、目視で正誤を確定させた16コマ）:
   tape05r 裂けあり 4コマ  10.5〜18.8% で検出   ○
   tape05r 正常     5コマ  すべて 0.0%          ○
   tape08  正常     5コマ  すべて 0.0%          ○
   tape05r 101s/102s は検出しない。あれは横の裂けではなく虹色・完全崩壊で、
   bin/vhschroma.py の担当（色差σ 24〜38）。ここで拾わないのが正しい。

判定
----
2つ満たしたコマだけを裂けとみなす。

  帯の幅     画面中央8割の中で、ほぼ真っ黒な列が連続する最大幅。
             既定は画面幅の3%以上。正常なコマは0%なので十分離れている。
  明るさ     コマ全体が暗いときは除く。フェードや無録画部は画面全体が
             黒く、裂けではない。テープ終端を巻き込まないための条件。

使い方
------
  vhstear.py <動画> --scan              分布を見る
  vhstear.py <動画> --out tears.json    捨てるコマの一覧を書き出す

出力の "select" は ffmpeg の select フィルタにそのまま渡せる式。
  -vf "select='<式>',fps=<元のコマ速度>"
捨てたぶんは fps が直前のコマを保持して埋める。
"""
import argparse, json, os, subprocess, sys
import numpy as np

AP = argparse.ArgumentParser()
AP.add_argument("src")
AP.add_argument("--pre", default="bwdif=mode=send_field:parity=tff,crop=746:480:4:4",
                help="判定前に通すフィルタ。納品と同じ見え方で測るため")
AP.add_argument("--w", type=int, default=320)
AP.add_argument("--h", type=int, default=240)
AP.add_argument("--dark", type=int, default=12, help="ほぼ真っ黒とみなす輝度")
# 2026-11-12 追加。これが無いと暗い場面で誤報を出す。
# tape08 の 1:03.6 / 27:08.6 / 45:07.7 を「帯22〜42%」と判定したが、
# 3つとも目で見ると完全に正常なコマだった。拾っていたのは暗い背景。
# 裂けの黒帯は画面の中に孤立して現れ、両側が明るい。暗い背景は画面の端まで
# 続く。だから「両側が十分明るいこと」を条件に加える。
AP.add_argument("--contrast", type=float, default=40.0,
                help="帯の少なくとも片側がこれだけ明るくないと裂けとみなさない")
AP.add_argument("--band", type=float, default=3.0, help="裂けとみなす帯の幅（画面幅に対する%%）")
AP.add_argument("--minlum", type=float, default=20.0, help="これより暗いコマは対象外")
AP.add_argument("--t1", type=float, default=None, help="この秒より後は対象外")
AP.add_argument("--scan", action="store_true")
AP.add_argument("--out", default=None)
AP.add_argument("--npy", default=None, help="コマごとの値を保存（しきい値の再検討用）")
A = AP.parse_args()

r = subprocess.run(["ffprobe","-v","error","-select_streams","v:0",
    "-show_entries","stream=avg_frame_rate","-of","csv=p=0", A.src],
    capture_output=True, text=True).stdout.strip()
n_, d_ = r.split("/"); SRCFPS = float(n_)/float(d_)
# bwdif send_field はコマ速度を倍にする
OUTFPS = SRCFPS*2 if "send_field" in A.pre else SRCFPS
print(f"入力 {A.src}\n  元 {SRCFPS:.4f}/秒 → 判定は {OUTFPS:.4f}/秒")

vf = f"{A.pre},scale={A.w}:{A.h}:flags=neighbor" if A.pre else f"scale={A.w}:{A.h}:flags=neighbor"
P = subprocess.Popen(["ffmpeg","-nostdin","-v","error","-i",A.src,
                      "-vf",vf,"-pix_fmt","gray","-f","rawvideo","-"],
                     stdout=subprocess.PIPE)
N = A.w*A.h
lo, hi = int(A.w*0.1), int(A.w*0.9)     # 端は元から黒いので中央8割を見る
band=[]; lum=[]
buf=b""
while True:
    c = P.stdout.read(N*16)
    if not c: break
    buf += c
    k = len(buf)//N
    for i in range(k):
        a = np.frombuffer(buf[i*N:(i+1)*N], dtype=np.uint8).astype(np.float32).reshape(A.h,A.w)
        cm = a.mean(axis=0)
        dark = (cm[lo:hi] < A.dark).astype(np.int8)
        dd = np.diff(np.concatenate(([0],dark,[0])))
        st = np.flatnonzero(dd==1); en = np.flatnonzero(dd==-1)
        best = 0
        W = hi-lo
        for u, v in zip(st, en):
            if u == 0 or v == W:      # 中央窓の端に接する＝外へ続いている。背景
                continue
            inner = cm[lo+u:lo+v].mean()
            L = cm[lo+max(0,u-10):lo+u].mean()
            R = cm[lo+v:lo+min(W,v+10)].mean()
            # 「両側が明るいこと」を条件にしてはいけない。裂けの黒帯は
            # 帰線期間なので、すぐ左は前の走査線の終わりで元々暗い。
            # tape05r の実測で、右側との差が43〜64あるのに左側は11〜30しかない。
            # 片側だけ見る。
            if max(L - inner, R - inner) < A.contrast:
                continue
            best = max(best, v-u)
        band.append(best)
        lum.append(float(a.mean()))
    buf = buf[k*N:]
P.stdout.close(); P.wait()

B = np.array(band, float)/(hi-lo)*100.0
L = np.array(lum)
T = np.arange(len(B))/OUTFPS
print(f"  {len(B)} コマ = {len(B)/OUTFPS:.1f} 秒\n")
print("=== 帯の幅の分布（画面幅%）===")
q = np.percentile(B,[50,90,99,99.5,99.9,100])
print(f"  中央値 {q[0]:.2f} | 90% {q[1]:.2f} | 99% {q[2]:.2f} | "
      f"99.9% {q[4]:.2f} | 最大 {q[5]:.2f}")
print(f"  3%超のコマ {int((B>3).sum())} / 1%超 {int((B>1).sum())} / 0超 {int((B>0).sum())}")

# 黒いコマ（無録画部・フェード）を外した上での分布。しきい値はここの谷に置く。
cand = L >= A.minlum
print(f"\n=== 明るさ {A.minlum} 以上のコマ {int(cand.sum())} 本における帯の幅 ===")
edges = [0,0.5,1,2,3,4,6,8,10,12,15,20,30,50,101]
for i in range(len(edges)-1):
    m = cand & (B >= edges[i]) & (B < edges[i+1])
    n = int(m.sum())
    if n: print(f"  {edges[i]:5.1f}%〜{edges[i+1]:5.1f}% : {n:6d} コマ"
                f"  {n/OUTFPS:7.2f}秒  {'#'*min(40,int(n/20))}")
if A.npy:
    np.save(A.npy, np.vstack([T,B,L]))
    print(f"  コマごとの値を保存: {A.npy}")

if A.scan:
    print("\n=== 帯の広いコマ上位25 ===")
    print("    時刻     帯%   明るさ  対象")
    for i in np.argsort(-B)[:25]:
        tgt = "○" if (B[i]>A.band and L[i]>=A.minlum and (A.t1 is None or T[i]<A.t1)) else "×"
        print(f"  {int(T[i])//60}:{T[i]%60:06.3f} {B[i]:7.2f} {L[i]:7.1f}   {tgt}")
    sys.exit(0)

hit = (B > A.band) & (L >= A.minlum)
if A.t1 is not None:
    hit &= (T < A.t1)
idx = np.flatnonzero(hit)
print(f"\n=== 捨てるコマ {len(idx)} / {len(B)} （{len(idx)/len(B)*100:.3f}%、"
      f"{len(idx)/OUTFPS:.2f}秒ぶん）===")
runs=[]
if len(idx):
    s=idx[0]; p=idx[0]
    for i in idx[1:]:
        if i-p>1: runs.append((s,p)); s=i
        p=i
    runs.append((s,p))
for a,b in runs:
    print(f"  {int(T[a])//60}:{T[a]%60:06.3f} 〜 {int(T[b])//60}:{T[b]%60:06.3f}  "
          f"{b-a+1:3d}コマ  帯 最大{B[a:b+1].max():.1f}%")
# select は「残すコマ」の条件なので否定で書く
expr = "+".join(f"between(n,{a},{b})" for a,b in runs)
sel = f"not({expr})" if expr else "1"
res = {"source": os.path.abspath(A.src), "out_fps": OUTFPS, "frames": len(B),
       "pre": A.pre, "band_threshold": A.band, "minlum": A.minlum, "t1": A.t1,
       "dropped": int(len(idx)),
       "runs": [{"start_frame": int(a), "end_frame": int(b),
                 "start": float(T[a]), "end": float(T[b]),
                 "band_max": float(B[a:b+1].max())} for a,b in runs],
       "select": sel, "version": 1}
if A.out:
    with open(A.out,"w") as f: json.dump(res,f,ensure_ascii=False,indent=1)
    print(f"\n書いた: {A.out}")
