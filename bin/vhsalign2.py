#!/usr/bin/env python3
"""同期測定の第2版。既存の vhsalign.py を置き換える前の検証用。

v1 との違い
-----------
1. 相関に画面全体を使う。
   v1 は 32x24=768 画素を mean(axis=1) で 1 フレーム 1 数値に潰してから
   相関していた。明るさの平均だけでは絵の中身が消えるため、動きの乏しい
   場面でピークが立たず、窓ごとの答えが数コマ単位でばらつく。
   v2 は 768 次元のまま相関させる。静止部分は窓内の画素ごと時間平均を
   引いて落とすので、効くのは「動いた所」だけになる。

2. 窓を 6 本 30 秒から 14 本 20 秒へ。
   tape06 で再測定したところ、採用 11/14 で窓ごとのばらつきは
   0.088 秒(2.6コマ)だった。v1 の 6 窓では採用 3/6、0.126 秒(3.8コマ)。

3. 合否をばらつきではなく中央値の標準誤差で見る。
   知りたいのは「最終的に採用する 1 つの値がどれだけ確かか」であって
   「個々の測定がどれだけ揃っているか」ではない。測定が n 個あれば
   中央値の不確かさは σ/√n の程度まで下がる。
   tape06 の実績:
       窓 3本  ばらつき 0.126 秒 → 標準誤差 0.073 秒 = 2.2 コマ
       窓11本  ばらつき 0.088 秒 → 標準誤差 0.027 秒 = 0.8 コマ
   既存のゲートは「ばらつき 1.0 コマ以内」なので、窓を増やしても
   永久に合格しない。見るべき量が違う。

4. ピーク位置を放物線で補間してサブフレーム精度を出す。

5. 想定ズレを与えて探索範囲を狭められる (--expect/--tol)。
   このリグでは収録スクリプトの待ちループが必ず 5.0 秒回りきるため、
   参照の先行は毎回 4.87〜5.13 秒に入る。遠くの偽ピークを最初から
   候補に入れない方が安全だが、既定では v1 と同じ全範囲を探す。

実測による検証 (2026-11-06)
---------------------------
既存の全テープを遡って測り直した。v1 の値は各テープの align.json から。
「長さ差」は内容を一切見ない独立の推定（参照映像とRF映像の長さの差）。

  テープ  v1のtrim v1窓 v1σ |  v2中央値 v2窓  v2σ  標準誤差 | 長さ差
  tape01    記録なし  -   -  |   +5.126 14/14 1.0コマ 0.3コマ | +5.142
  tape03    5.0917    4  0.7 |   +5.092 13/14 1.4コマ 0.5コマ | +5.144
  tape04    4.8748    4  0.8 |   +4.893 14/14 1.4コマ 0.5コマ | +4.821
  tape05    5.1251    2  1.0 |   +5.160 14/14 0.9コマ 0.3コマ | +5.125
  tape06    5.0917    3  3.8 |   +5.043 14/14 2.2コマ 0.7コマ | +5.070
  tape07    5.0580    5  3.0 |   +5.093 14/14 0.5コマ 0.2コマ | +4.957

読み取れたこと:

  * v2 は v1 の答えを壊していない。差は最大 1.5 コマ以内で、
    目視で合格を出した tape06 の値も再現する。
  * v2 は独立な長さ差推定と 6 本中 5 本で 0.072 秒以内に一致する。
    内容相関と長さ比較という別経路が同じ数字を出すので、
    どちらかの系統誤差ではない。
  * v1 のばらつきが小さく見えたのは採択の副作用。MIN_PEAK/MIN_RATIO が
    窓をほとんど捨てていた（tape05 は 2 本、tape06 は 3 本）。
    2 本しか残らなければばらつきは小さくなるしかない。v2 は 13〜14 本を
    採るので、難しい場面まで標本に入って σ は正直に大きくなる。
  * 既存のゲート（σ 1.0 コマ以内）を v2 の σ にかけると 6 本中 3 本が
    不合格になる。その 1 本は tape06、つまり人が目で見て
    「全く問題ない」と判断して納品した本。ゲートは納品可能なものを
    落とす量を見ている。標準誤差で見れば 6 本すべて 0.2〜0.7 コマ。

tape07 はこの検証の後、v1 の 5.058 秒で納品した。完成品の音ズレ実測は
100秒 -66ms / 850秒 -23ms / 1600秒 -34ms（相関 0.997 以上）で、
放送の許容 -125〜+45ms の内側。v2 の値との差 35ms は知覚されない。

本番には繋いでいない。ゲートの基準はマスターが決めるものなので、
vhsalign.py は触らず、この第2版を別経路として置いてある。

向きの約束は v1 と同じ。trim_sec は「参照映像の先頭から切り落とす秒数」。
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

W, H = 32, 24          # 相関に使う縮小サイズ。--grid で変えられる
# 格子の粗さには二律背反がある。細かいほど絵の位置情報は増えるが、動いて
# いない画素はノイズしか載せないので相関の底上げになる。粗いほど画素平均
# でノイズが√Nに薄まるが、位置情報が消える。v1 は 32x24 を 1 画素まで
# 潰していた（= 極端に粗い側）。実データで掃いて決める。
NWIN = 14              # 窓の数
WIN = 20.0             # 1つの窓の長さ(秒)
MARGIN = 20.0          # 参照側に前後へ取る余裕(秒)
MIN_PEAK = 0.60        # 一致の質。これ未満の窓は中身が合っていない
OUT_LIMIT = 0.50       # 中央値からこれ(秒)以上離れた窓は外れ値として捨てる
SIGMA_FLOOR = 0.5      # σの下限(コマ)。全窓が同じ答えでも量子化分の不確かさは残る
DRIFT_LIMIT = 0.005    # 現実的なクロック差の上限(±0.5%)
SE_MAX_FRAMES = 1.0    # 中央値の標準誤差の許容値(コマ)
MIN_WINDOWS = 6        # これだけ採用できないと信用しない


def probe(path, entries, stream=None):
    cmd = ["ffprobe", "-v", "error"]
    if stream:
        cmd += ["-select_streams", stream]
    cmd += ["-show_entries", entries, "-of", "default=nw=1:nk=1", str(path)]
    return subprocess.run(cmd, capture_output=True, text=True).stdout.split()


def fps_of(path):
    a, b = (probe(path, "stream=r_frame_rate", "v:0")[0].split("/") + ["1"])[:2]
    return float(a) / float(b)


def duration_of(path):
    return float(probe(path, "format=duration")[0])


def frames(path, start, length, tmpdir):
    """指定区間を (フレーム数, W*H) の float 配列で返す。

    ffv1 に一旦落とすのは v1 と同じ理由。-ss の丸めや並べ替えに
    左右されず、確実にフレーム順で読むため。
    """
    tmp = Path(tmpdir) / "w.mkv"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{start}",
                    "-i", str(path), "-t", f"{length}", "-an",
                    "-c:v", "ffv1", "-y", str(tmp)], check=True)
    raw = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(tmp),
                          "-vf", f"scale={W}:{H},format=gray",
                          "-f", "rawvideo", "-"], capture_output=True).stdout
    buf = np.frombuffer(raw, np.uint8)
    n = len(buf) // (W * H)
    if n == 0:
        return np.empty((0, W * H))
    return buf[:n * W * H].reshape(n, W * H).astype(np.float64)


def ncc_frames(T, S, lo=None, hi=None):
    """画面全体を使った正規化相互相関。

    窓内で画素ごとの時間平均を引く。静止している部分は 0 になるので、
    相関に寄与するのは時間方向に変化した画素だけになる。
    テンプレート側の平均を引いてあれば分子で参照側の平均は打ち消える
    ので、参照側は分母のノルムだけ窓ごとに計算すればよい。

    (lag(サブフレーム), ピーク値, 2位との比) を返す。
    """
    n = len(T)
    if n < 60 or len(S) <= n:
        return None
    Tc = T - T.mean(axis=0)
    tz = float(np.sqrt((Tc ** 2).sum()))
    if tz < 1e-9:
        return None

    nlag = len(S) - n + 1
    lo = 0 if lo is None else max(0, lo)
    hi = nlag if hi is None else min(nlag, hi + 1)
    if hi - lo < 3:
        return None

    # 参照側のノルムは累積和から出す（窓ごとに引き算をやり直さない）
    c1 = np.vstack([np.zeros(S.shape[1]), np.cumsum(S, axis=0)])
    c2 = np.vstack([np.zeros(S.shape[1]), np.cumsum(S ** 2, axis=0)])

    vals = np.full(nlag, -1.0)
    for k in range(lo, hi):
        num = float(np.tensordot(Tc, S[k:k + n], axes=([0, 1], [0, 1])))
        s1 = c1[k + n] - c1[k]
        s2 = c2[k + n] - c2[k]
        sz2 = float((s2 - s1 ** 2 / n).sum())
        vals[k] = num / (tz * np.sqrt(sz2)) if sz2 > 1e-9 else 0.0

    j = int(vals.argmax())
    peak = float(vals[j])

    # 2位。ピーク近傍(±30コマ=約1秒)は同じ山なので除く
    mask = np.zeros(nlag, bool)
    mask[lo:hi] = True
    mask[max(lo, j - 30):j + 31] = False
    second = float(vals[mask].max()) if mask.any() else 0.0
    ratio = peak / (abs(second) + 1e-9)

    # 放物線補間でサブフレーム精度。両隣が探索範囲内にあるときだけ
    lag = float(j)
    if lo < j < hi - 1:
        y0, y1, y2 = vals[j - 1], vals[j], vals[j + 1]
        den = y0 - 2 * y1 + y2
        if abs(den) > 1e-12:
            lag = j + 0.5 * (y0 - y2) / den
    return lag, peak, ratio


def robust_center(ds, fps):
    """中央値と、その標準誤差。

    σ は中央絶対偏差から出す(1.4826 倍で正規分布の標準偏差に対応)。
    外れ値 1 つで壊れないため。中央値の標準誤差は正規分布なら
    σ/√n の 1.2533 倍。

    全窓が同じ答えを返しても σ=0 とはしない。測定はコマ単位に量子化
    されているので、少なくともその分の不確かさは残っている。標本標準
    偏差で代用すると外れ値 1 つで汚れるため、下限として与える。
    """
    med = float(np.median(ds))
    mad = float(np.median(np.abs(ds - med)))
    sigma = max(1.4826 * mad, SIGMA_FLOOR / fps)
    se = 1.2533 * sigma / np.sqrt(len(ds))
    return med, sigma, se


def main():
    global W, H
    ap = argparse.ArgumentParser()
    ap.add_argument("rf_video")
    ap.add_argument("ref_video")
    ap.add_argument("--nwin", type=int, default=NWIN)
    ap.add_argument("--win", type=float, default=WIN)
    ap.add_argument("--margin", type=float, default=MARGIN)
    ap.add_argument("--expect", type=float, default=None,
                    help="想定ズレ(秒)。与えると探索範囲を絞る")
    ap.add_argument("--tol", type=float, default=1.5,
                    help="--expect からの許容幅(秒)")
    ap.add_argument("--grid", default=f"{W}x{H}",
                    help="相関に使う縮小サイズ(例 8x6)。粗いほどノイズに強い")
    ap.add_argument("--out", default="/tmp/vhsalign2.json")
    a = ap.parse_args()

    W, H = (int(v) for v in a.grid.lower().split("x"))

    fps = fps_of(a.rf_video)
    dur_rf = duration_of(a.rf_video)
    dur_ref = duration_of(a.ref_video)
    print(f"  RF映像  : {dur_rf:8.2f} 秒  {fps:.3f} fps")
    print(f"  参照映像: {dur_ref:8.2f} 秒  {fps_of(a.ref_video):.3f} fps")
    print(f"  窓 {a.nwin}本 x {a.win:.0f}秒  格子 {W}x{H}  探索±{a.margin:.0f}秒", end="")
    if a.expect is not None:
        print(f"  （{a.expect:+.3f}±{a.tol:.1f}秒に限定）")
    else:
        print()

    # 参照とRFの長さの差は、収録の開始ずれそのもの（停止は同時）。
    # 相関と独立した見積もりなので突き合わせに使える。
    print(f"  長さの差から見た開始ずれ: {dur_ref - dur_rf:+.3f} 秒")

    # 窓は RF 側にも参照側にも収まらなければならない。参照側は
    # [t-margin, t+win+margin] を切り出すので、末尾に margin の余裕が要る。
    # ここを見ていないと最後の窓で参照が足りず、探索が範囲の縁に
    # 張り付いて無関係な値を返す（v1 はこれで毎回 1 窓を無駄にしていた）。
    span = min(dur_rf - a.win, dur_ref - a.win - a.margin) - a.margin
    if span <= 0:
        print("  映像が短すぎて窓を置けない。無補正にする")
        return dump(a.out, 0.0, 0, 1.0, 0.0, "測定不能", fps)
    starts = [a.margin + span * i / (a.nwin - 1) for i in range(a.nwin)]

    lo = hi = None
    if a.expect is not None:
        lo = int(np.floor((a.margin + a.expect - a.tol) * fps))
        hi = int(np.ceil((a.margin + a.expect + a.tol) * fps))

    rows = []
    print("\n  RF時刻    ズレ(秒)   相関   2位比")
    with tempfile.TemporaryDirectory() as td:
        for t in starts:
            A = frames(a.rf_video, t, a.win, td)
            B = frames(a.ref_video, t - a.margin, a.win + 2 * a.margin, td)
            r = ncc_frames(A, B, lo, hi)
            if r is None:
                continue
            lag, peak, ratio = r
            d = (t - a.margin + lag / fps) - t
            rows.append((t, d, peak, ratio, peak >= MIN_PEAK))
            print(f"  {t:7.1f}秒  {d:+8.3f}  {peak:.4f}  {ratio:5.2f}"
                  f"  {'' if peak >= MIN_PEAK else '← 一致が弱い'}")

    # 1段目: 一致の質で落とす。
    # 2位比は参考値として出すだけで、採否には使わない。v1 は 1 窓だけで
    # 「競合があるか」を判断しようとして閾値を外した。全画面相関では
    # ピークも 2 位も高い値に寄るため比そのものが縮む。競合の有無は
    # 窓どうしの一致（下の標準誤差）で決まる。
    ok1 = [r for r in rows if r[4]]
    if len(ok1) < 3:
        print(f"\n  一致した窓が {len(ok1)} 本しかない。無補正にする")
        return dump(a.out, 0.0, 0, 1.0, 0.0, "測定不能", fps,
                    used=len(ok1), total=len(rows))

    # 2段目: 中央値から離れすぎた窓を捨てる。
    # 端の窓は参照側が足りず、探索が範囲の縁に張り付いて無関係な値を返す。
    med0 = float(np.median([r[1] for r in ok1]))
    use = [r for r in ok1 if abs(r[1] - med0) <= OUT_LIMIT]
    dropped = [r for r in ok1 if abs(r[1] - med0) > OUT_LIMIT]
    for r in dropped:
        print(f"  {r[0]:7.1f}秒  {r[1]:+8.3f}  ← 中央値から{abs(r[1]-med0):.2f}秒離れたので捨てる")
    print(f"\n  採用した窓 {len(use)}/{len(rows)}")
    if len(use) < 3:
        print("  窓が足りない。無補正にする")
        return dump(a.out, 0.0, 0, 1.0, 0.0, "測定不能", fps,
                    used=len(use), total=len(rows))

    ts = np.array([r[0] for r in use])
    ds = np.array([r[1] for r in use])
    trim, sigma, se = robust_center(ds, fps)
    print(f"  ズレの中央値 {trim:+.3f} 秒")
    print(f"  ばらつき(σ)  {sigma:.3f} 秒 = {sigma * fps:.1f} コマ   ← v1が見ていた量")
    print(f"  標準誤差     {se:.3f} 秒 = {se * fps:.1f} コマ   ← v2が見る量")

    drift, note = 1.0, "窓が足りないので無補正"
    if len(use) >= 3 and np.ptp(ts) > 300:
        slope = float(np.polyfit(ts, ds, 1)[0])
        if abs(slope) > DRIFT_LIMIT:
            note = f"算出値が現実的な範囲(±{DRIFT_LIMIT:.1%})を外れたので無補正"
        else:
            drift = 1.0 - slope
            note = f"傾き {slope * 3600:+.3f} 秒/時 から算出"
    print(f"  速度比: {drift:.7f}  （{note}）")

    if se * fps <= SE_MAX_FRAMES and len(use) >= MIN_WINDOWS:
        conf = "高い"
    elif se * fps <= 2 * SE_MAX_FRAMES and len(use) >= 3:
        conf = "中くらい"
    else:
        conf = "低い"
    print(f"  判定: {conf}"
          f"  （合格条件: 標準誤差 {SE_MAX_FRAMES:.1f}コマ以内 かつ 窓{MIN_WINDOWS}本以上）")

    return dump(a.out, trim, int(round(trim * fps)), drift,
                float(np.mean([r[2] for r in use])), conf, fps,
                float(np.mean([r[3] for r in use])), len(use), len(rows),
                sigma, se, se * fps, dur_ref - dur_rf)


def dump(path, trim_sec, offset_frames, drift, peak, conf, fps,
         ratio=0.0, used=0, total=0, spread=0.0, se=0.0, se_frames=0.0,
         dur_diff=0.0):
    json.dump({"trim_sec": trim_sec, "offset_frames": offset_frames,
               "drift": drift, "fps": fps, "peak": peak,
               "confidence": conf, "peak_ratio": ratio,
               "windows_used": used, "windows_total": total,
               "spread_sec": spread,
               "se_sec": se, "se_frames": se_frames,
               "duration_diff_sec": dur_diff,
               "grid": f"{W}x{H}",
               "version": 2},
              open(path, "w"))


if __name__ == "__main__":
    sys.exit(main())
