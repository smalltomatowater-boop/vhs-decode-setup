#!/usr/bin/env python3
"""
dec.tbc.json からドロップアウトの「位置」を取り出して、テープの傷み方を診断する。

なぜ要るか
----------
tbc-video-export は最後に「... with N dropout concealments.」と総数だけ出す。
総数は本と本の比較には使えるが、原因の切り分けには足りない。2026-11-12 に
「FANATIC◇CRISIS Truth のテープ自体が悪いのか」を問われて、答えられなかった。
位置は dec.tbc.json に入っているのに vhsclean が消していて、原本も消していた。

何が分かるか
------------
dec.tbc.json の各フィールドには、あれば dropOuts が入る（実装で確認済。
tools/library/tbc/dropouts.cpp の write()）:

    "dropOuts": { "startx":[...], "endx":[...], "fieldLine":[...] }

3本の並列配列で、1件が1つの傷。startx/endx は横位置（標本）、fieldLine は
フィールド内の行番号。これを時間軸・縦位置・横位置・ヘッド別に積み直す。

一番効くのは **ヘッド別の偏り**。VHSの2ヘッドデッキはヘッドAとBが1
フィールドずつ交互に読むので、isFirstField がヘッドの別名になる。

  両パリティに均等      → テープ側の傷
  片パリティに偏る      → デッキのヘッドが汚れ/摩耗。テープは無罪
  時間軸で特定箇所に密集 → 折れ・シワ。その箇所だけ録り直す価値がある
  巻頭・巻末に集中       → 取り扱いの傷。中身は無事
  全体に均一            → テープ素材の劣化
  縦位置が特定行に集中   → ヘッド切替やトラッキングの問題

使い方
------
  vhsdropouts.py <dec.tbc.json> [--json 出力先] [--bins 分割数]

断定はしない。数字と形を出すだけ。判断は人がする。
"""
import argparse, json, math, os, sys

AP = argparse.ArgumentParser()
AP.add_argument("src", help="dec.tbc.json")
AP.add_argument("--json", default=None, help="要約の書き出し先（既定は書かない）")
# 生の総数には「テープの傷ではないもの」が混ざる。2026-11-12 tape05r で、
# 566件の半分が最後の1分、うち129件が1秒に集中していた。そこは録画の
# 終わりで信号が切れた点であって傷ではない。縦位置も下端30行に偏るが、
# そこはヘッド切替点で毎フィールド必ず荒れる。窓を切って測り直せるようにする。
AP.add_argument("--t0", type=float, default=None, help="この秒より前を除く")
AP.add_argument("--t1", type=float, default=None, help="この秒より後を除く")
AP.add_argument("--lmin", type=int, default=None, help="この行より上を除く(fieldLine)")
AP.add_argument("--lmax", type=int, default=None, help="この行より下を除く(fieldLine)")
AP.add_argument("--bins", type=int, default=0, help="時間軸の分割数（既定は1分ごと）")
A = AP.parse_args()

if not os.path.isfile(A.src):
    sys.exit(f"無い: {A.src}")

sz = os.path.getsize(A.src)
print(f"読む {A.src}  ({sz/2**20:.0f} MiB)")
with open(A.src, "rb") as f:
    J = json.load(f)

vp = J.get("videoParameters", {})
fields = J.get("fields", [])
if not fields:
    sys.exit("fields が空。これは dec.tbc.json ではないか、壊れている")

pal = bool(vp.get("isSourcePal", False))
FIELD_RATE = 50.0 if pal else 60000.0/1001.0
FW = vp.get("fieldWidth"); FH = vp.get("fieldHeight")
print(f"  {'PAL' if pal else 'NTSC'}  フィールド {len(fields)} 本"
      f"  = {len(fields)/FIELD_RATE/60:.1f} 分"
      f"  1フィールド {FW}x{FH}")

# ---- 積み直し -------------------------------------------------------------
n_regions = 0          # 傷の件数
n_samples = 0          # 傷が覆った標本の総数
fields_hit = 0         # 傷が1件以上あったフィールド数
per_field = [0]*len(fields)          # フィールドごとの件数
per_field_w = [0]*len(fields)        # フィールドごとの標本数
parity = {True: [0,0,0], False: [0,0,0]}   # isFirstField -> [件数, 標本数, フィールド数]
line_hist = {}
startx_hist = {}
width_hist = {}
burst = [None]*len(fields)

T0 = 0 if A.t0 is None else int(A.t0*FIELD_RATE)
T1 = len(fields) if A.t1 is None else int(A.t1*FIELD_RATE)
LMIN = -10**9 if A.lmin is None else A.lmin
LMAX =  10**9 if A.lmax is None else A.lmax
if A.t0 is not None or A.t1 is not None or A.lmin is not None or A.lmax is not None:
    print(f"  窓: {T0/FIELD_RATE:.1f}〜{T1/FIELD_RATE:.1f}秒 / 行 "
          f"{'先頭' if A.lmin is None else A.lmin}〜"
          f"{'末尾' if A.lmax is None else A.lmax}")

for i, fl in enumerate(fields):
    ff = bool(fl.get("isFirstField", i % 2 == 0))
    if not (T0 <= i < T1):
        continue
    b = fl.get("medianBurstIRE")
    if isinstance(b, (int, float)):
        burst[i] = float(b)
    parity[ff][2] += 1
    do = fl.get("dropOuts")
    if not do:
        continue
    sx = do.get("startx", []); ex = do.get("endx", []); ln = do.get("fieldLine", [])
    k = min(len(sx), len(ex), len(ln))
    if k == 0:
        continue
    w_sum = 0
    kept = 0
    for j in range(k):
        if not (LMIN <= ln[j] <= LMAX):
            continue
        kept += 1
        w = max(0, ex[j] - sx[j])
        w_sum += w
        line_hist[ln[j]] = line_hist.get(ln[j], 0) + 1
        startx_hist[sx[j] // 64] = startx_hist.get(sx[j] // 64, 0) + 1
        wb = 0 if w == 0 else min(int(math.log2(w)) , 14)
        width_hist[wb] = width_hist.get(wb, 0) + 1
    if kept == 0:
        continue
    fields_hit += 1
    n_regions += kept
    per_field[i] = kept
    parity[ff][0] += kept
    n_samples += w_sum
    per_field_w[i] = w_sum
    parity[ff][1] += w_sum

NF = len(fields)
print()
print("=== 総量 ===")
print(f"  傷の件数            {n_regions}")
print(f"  傷のあったフィールド {fields_hit} / {NF}  ({fields_hit/NF*100:.1f}%)")
print(f"  覆われた標本の総数   {n_samples}")
if FW:
    print(f"  1フィールドの全標本に対する割合 {n_samples/(NF*FW*(FH or 1))*100:.4f}%")
print(f"  1000フィールドあたりの件数 {n_regions/NF*1000:.1f}")

# ---- ヘッド別（これが本命） -----------------------------------------------
print()
print("=== ヘッド別の偏り（isFirstField = 回転ヘッドの別名）===")
tot = parity[True][0] + parity[False][0]
for ff in (True, False):
    c, s, n = parity[ff]
    nm = "ヘッドA (isFirstField=true )" if ff else "ヘッドB (isFirstField=false)"
    r = c/n*1000 if n else 0
    sh = c/tot*100 if tot else 0
    print(f"  {nm}: {c:8d} 件 ({sh:5.1f}%)  1000フィールドあたり {r:7.1f}  標本 {s}")
if tot and min(parity[True][0], parity[False][0]) > 0:
    hi = max(parity[True][0], parity[False][0]); lo = min(parity[True][0], parity[False][0])
    ratio = hi/lo
    print(f"  偏り {ratio:.2f} 倍")
    if ratio < 1.3:
        print("  → 両ヘッドでほぼ同じ。デッキのヘッドは容疑から外れる。テープ側の傷")
    elif ratio < 2.0:
        print("  → 中くらいの偏り。ヘッドの片方が弱っている可能性。断定はできない")
    else:
        print("  → 強い偏り。片方のヘッドが汚れ/摩耗の疑い。テープより先にデッキを見る")
else:
    print("  → 片側しか傷が無い。偏りの計算はしない")

# ---- 時間軸 ---------------------------------------------------------------
dur = NF/FIELD_RATE
nb = A.bins if A.bins > 0 else max(1, int(dur/60))
step = NF/nb
prof = []
for b in range(nb):
    lo = int(b*step); hi = int((b+1)*step)
    c = sum(per_field[lo:hi]); nfb = max(1, hi-lo)
    bs = [x for x in burst[lo:hi] if x is not None]
    prof.append((lo/FIELD_RATE, hi/FIELD_RATE, c, c/nfb*1000,
                 (sum(bs)/len(bs)) if bs else None))
mx = max((p[3] for p in prof), default=0)
print()
print(f"=== 時間軸の分布（{nb}分割、1000フィールドあたりの件数）===")
print("     時刻        件数   密度   バースト  ")
for s, e, c, d, bv in prof:
    bar = "#" * int(round(d/mx*40)) if mx else ""
    bt = f"{bv:6.1f}" if bv is not None else "    - "
    print(f"  {int(s)//60:3d}:{int(s)%60:02d}  {c:8d} {d:7.1f} {bt}  {bar}")

# ---- 縦位置 ---------------------------------------------------------------
print()
print("=== 縦位置（fieldLine）の偏り ===")
if line_hist:
    lines = sorted(line_hist)
    lo, hi = lines[0], lines[-1]
    nbl = 24
    w = max(1, (hi-lo+1)/nbl)
    bands = [0]*nbl
    for L, c in line_hist.items():
        bands[min(nbl-1, int((L-lo)/w))] += c
    mb = max(bands)
    for b in range(nbl):
        a0 = int(lo + b*w); a1 = int(lo + (b+1)*w) - 1
        bar = "#" * int(round(bands[b]/mb*40)) if mb else ""
        print(f"  行 {a0:4d}〜{a1:4d}: {bands[b]:8d}  {bar}")
    top = sorted(line_hist.items(), key=lambda kv: -kv[1])[:8]
    print("  多い行: " + "  ".join(f"{L}行={c}件" for L, c in top))
else:
    print("  傷なし")

# ---- 横位置と幅 -----------------------------------------------------------
print()
print("=== 横位置（startx、64標本ごと）上位12 ===")
for k, c in sorted(startx_hist.items(), key=lambda kv: -kv[1])[:12]:
    print(f"  標本 {k*64:5d}〜{k*64+63:5d}: {c:8d} 件")
print()
print("=== 傷の幅の分布（標本数、2のべき乗で束ねた）===")
for k in sorted(width_hist):
    lo = 2**k; hi = 2**(k+1)-1
    print(f"  {lo:6d}〜{hi:6d} 標本: {width_hist[k]:8d} 件")

# ---- 最悪の区間 -----------------------------------------------------------
print()
print("=== 密集している上位10秒 ===")
sec = {}
for i, c in enumerate(per_field):
    if c:
        sec[int(i/FIELD_RATE)] = sec.get(int(i/FIELD_RATE), 0) + c
for t, c in sorted(sec.items(), key=lambda kv: -kv[1])[:10]:
    print(f"  {t//60:3d}:{t%60:02d}  {c:6d} 件")

# ---- 書き出し -------------------------------------------------------------
if A.json:
    out = {
        "source": os.path.abspath(A.src),
        "system": "PAL" if pal else "NTSC",
        "field_rate": FIELD_RATE,
        "fields": NF,
        "duration_sec": dur,
        "field_width": FW, "field_height": FH,
        "regions": n_regions,
        "samples": n_samples,
        "fields_hit": fields_hit,
        "per_1000_fields": n_regions/NF*1000,
        "parity": {"first": parity[True], "second": parity[False]},
        "profile": [{"start": s, "end": e, "regions": c,
                     "per_1000": d, "burst_ire": bv} for s, e, c, d, bv in prof],
        "line_hist": {str(k): v for k, v in sorted(line_hist.items())},
        "startx_hist_64": {str(k*64): v for k, v in sorted(startx_hist.items())},
        "width_hist_log2": {str(k): v for k, v in sorted(width_hist.items())},
        "version": 1,
    }
    os.makedirs(os.path.dirname(os.path.abspath(A.json)), exist_ok=True)
    with open(A.json, "w") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"\n要約を書いた: {A.json}")
