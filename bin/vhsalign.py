#!/usr/bin/env python3
"""RF復号映像と参照キャプチャ映像を突き合わせて、ズレ(秒)と速度比を求める。

測り方
------
テープ全体に 30 秒の窓を複数置き、窓ごとに正規化相互相関でズレを求める。
窓ごとの答えが揃えばその値が正解。時刻に対して傾いていればクロックドリフト。

なぜ窓方式か
------------
以前は全フレームの輝度系列を一度に相関させていたが、似た絵が何度も出てくる
素材では候補が競合して位置を外す。実際 28 分のテープで

    全体一括 : +4.671 秒  相関 0.862  2位との比 1.06（信頼度「低い」）
    窓方式   : +5.13  秒  6窓すべて +5.03〜+5.16 でばらつき 1.5 コマ

と 14 コマ(0.46秒)ずれた答えを返し、気づかなければ音ズレ品になっていた。
窓方式は副作用として速くもなる。19GB を丸ごと復号する必要がなく、
必要な区間だけ切り出すので 10 分かかっていた測定が 1 分で終わる。

向きの約束
----------
trim_sec は「参照映像の先頭から切り落とす秒数」。参照のほうが先に録り
始まっている場合に正の値になる。ffmpeg の -itsoffset は逆方向なので、
取り違えないよう用途そのものを名前にしてある。
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

W, H = 32, 24          # 相関に使う縮小サイズ。小さいほうが絵柄の細部に惑わされない
WIN = 30.0             # 1つの窓の長さ(秒)
MARGIN = 20.0          # 参照側に前後へ取る余裕(秒)。想定しうるズレより大きくすること
NWIN = 6               # 窓の数
MIN_PEAK = 0.90        # これ未満の相関しか出ない窓は使わない
MIN_RATIO = 1.20       # 2位との比。似た位置が競合している窓は使わない
DRIFT_LIMIT = 0.005    # 現実的なクロック差の上限(±0.5%)


def probe(path, entries, stream=None):
    cmd = ["ffprobe", "-v", "error"]
    if stream:
        cmd += ["-select_streams", stream]
    cmd += ["-show_entries", entries, "-of", "default=nw=1:nk=1", str(path)]
    return subprocess.run(cmd, capture_output=True, text=True).stdout.split()


def fps_of(path):
    out = probe(path, "stream=r_frame_rate", "v:0")
    a, b = (out[0].split("/") + ["1"])[:2]
    return float(a) / float(b)


def duration_of(path):
    return float(probe(path, "format=duration")[0])


def luma_window(path, start, length, tmpdir):
    """指定区間を切り出して、1フレームあたりの平均輝度の時系列を返す。

    ffv1 で一旦ファイルに落とすのは、-ss の丸めや B フレームの並べ替えに
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
        return np.empty(0)
    return buf[:n * W * H].reshape(n, W * H).mean(axis=1).astype(np.float64)


def ncc(tmpl, sig):
    """正規化相互相関。窓ごとに平均と分散を取り直すので値は -1〜1 に収まる。
    (lag, ピーク値, 2位との比) を返す"""
    n = len(tmpl)
    if n < 60 or len(sig) <= n:
        return None
    tn = tmpl - tmpl.mean()
    tz = np.sqrt((tn ** 2).sum())
    if tz < 1e-9:
        return None
    vals = np.empty(len(sig) - n + 1)
    for k in range(len(vals)):
        s = sig[k:k + n]
        sn = s - s.mean()
        sz = np.sqrt((sn ** 2).sum())
        vals[k] = (tn @ sn) / (tz * sz) if sz > 1e-9 else 0.0
    j = int(vals.argmax())
    mask = np.ones(len(vals), bool)
    mask[max(0, j - 30):j + 31] = False
    second = float(vals[mask].max()) if mask.any() else 0.0
    return j, float(vals[j]), float(vals[j] / (abs(second) + 1e-9))


def main(rf_video, ref_video):
    fps = fps_of(rf_video)
    dur_rf = duration_of(rf_video)
    dur_ref = duration_of(ref_video)
    print(f"  RF映像  : {dur_rf:8.2f} 秒  {fps:.3f} fps")
    print(f"  参照映像: {dur_ref:8.2f} 秒  {fps_of(ref_video):.3f} fps")

    span = dur_rf - WIN - MARGIN
    if span <= 0:
        print("  映像が短すぎて窓を置けない。無補正にする")
        return dump(0.0, 0, 1.0, 0.0, "測定不能", fps)
    starts = [MARGIN + span * i / (NWIN - 1) for i in range(NWIN)]

    rows = []
    print("\n  RF時刻    ズレ(秒)   相関   2位比")
    with tempfile.TemporaryDirectory() as td:
        for t in starts:
            a = luma_window(rf_video, t, WIN, td)
            b = luma_window(ref_video, t - MARGIN, WIN + 2 * MARGIN, td)
            r = ncc(a, b)
            if r is None:
                continue
            k, peak, ratio = r
            d = (t - MARGIN + k / fps) - t
            good = peak >= MIN_PEAK and ratio >= MIN_RATIO
            rows.append((t, d, peak, ratio, good))
            print(f"  {t:7.1f}秒  {d:+8.3f}  {peak:.4f}  {ratio:5.2f}"
                  f"  {'' if good else '← 使わない'}")

    use = [r for r in rows if r[4]]
    print(f"\n  採用した窓 {len(use)}/{len(rows)}")
    if not use:
        print("  どの窓も信用できない。無補正にする")
        print("    ※ 映像の変化が乏しいと位置を特定しにくい。"
              "できた動画の音ズレを必ず確認すること")
        return dump(0.0, 0, 1.0, 0.0, "測定不能", fps)

    ts = np.array([r[0] for r in use])
    ds = np.array([r[1] for r in use])
    trim = float(np.median(ds))
    spread = float(ds.std())
    print(f"  ズレの中央値 {trim:+.3f} 秒   ばらつき {spread:.3f} 秒"
          f" = {spread * fps:.1f} コマ")

    # 速度比。ズレが時刻に対して傾いていればクロック差。
    drift, note = 1.0, "窓が足りないので無補正"
    if len(use) >= 3 and np.ptp(ts) > 300:
        slope = float(np.polyfit(ts, ds, 1)[0])
        if abs(slope) > DRIFT_LIMIT:
            note = f"算出値が現実的な範囲(±{DRIFT_LIMIT:.1%})を外れたので無補正"
        else:
            drift = 1.0 - slope
            note = f"傾き {slope * 3600:+.3f} 秒/時 から算出"
    print(f"  速度比: {drift:.7f}  （{note}）")

    # 信頼度。窓の一致度がそのまま信頼度になる。
    if spread * fps <= 3 and len(use) >= 4:
        conf = "高い"
    elif spread * fps <= 10 and len(use) >= 3:
        conf = "中くらい"
    else:
        conf = "低い"
    print(f"  信頼度: {conf}")
    if conf == "低い":
        print("    ※ できた動画の音ズレを必ず確認すること")

    peak = float(np.mean([r[2] for r in use]))
    return dump(trim, int(round(trim * fps)), drift, peak, conf, fps,
                float(np.mean([r[3] for r in use])), len(use), len(rows), spread)


def dump(trim_sec, offset_frames, drift, peak, conf, fps,
         ratio=0.0, used=0, total=0, spread=0.0):
    json.dump({"trim_sec": trim_sec, "offset_frames": offset_frames,
               "drift": drift, "fps": fps, "peak": peak,
               "confidence": conf, "peak_ratio": ratio,
               "windows_used": used, "windows_total": total,
               "spread_sec": spread},
              open("/tmp/vhsalign.json", "w"))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
