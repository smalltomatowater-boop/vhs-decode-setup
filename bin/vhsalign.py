#!/usr/bin/env python3
"""RF復号映像と参照キャプチャ映像を突き合わせて、ズレ(秒)と速度比を求める。

輝度の時間変化を相互相関にかけてフレーム単位のオフセットを出す。
速度比（クロックドリフト）は、前半と後半で別々にズレを測り、その差から
求める。全体の再生時間の比で出すと、収録開始タイミングの差を
ドリフトと誤認するので使わない。
"""
import subprocess, sys, json
import numpy as np

W, H = 32, 24
DRIFT_LIMIT = 0.005     # 現実的なクロック差の上限（±0.5%）。超えたら測定失敗とみなす
WINDOW_MIN_CORR = 0.35  # 前後の窓がこれ以下の相関しか出なければ速度比は信用しない


def luma_series(path):
    """1フレームあたりの平均輝度の時系列"""
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path,
         "-vf", f"scale={W}:{H},format=gray", "-f", "rawvideo", "-"],
        capture_output=True)
    buf = np.frombuffer(p.stdout, dtype=np.uint8)
    n = len(buf) // (W * H)
    if n == 0:
        raise RuntimeError(f"フレームを読めません: {path}")
    return buf[:n * W * H].reshape(n, W * H).mean(axis=1).astype(np.float64)


def fps_of(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=r_frame_rate", "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True).stdout.strip()
    a, b = (out.split("/") + ["1"])[:2]
    return float(a) / float(b)


def norm(x):
    s = x.std()
    return (x - x.mean()) / (s if s > 1e-9 else 1.0)


def ncc(tmpl, sig, lo, hi):
    """正規化相互相関。窓ごとに平均と分散を取り直すので値は必ず -1〜1 に収まる。
    (lag, ピーク値, 2位との比) を返す"""
    n = len(tmpl)
    lo = max(0, lo)
    hi = min(len(sig) - n, hi)
    if hi <= lo:
        return None
    tn = tmpl - tmpl.mean()
    ts = np.sqrt((tn ** 2).sum())
    if ts < 1e-9:
        return None
    vals = np.empty(hi - lo + 1)
    for i, k in enumerate(range(lo, hi + 1)):
        s = sig[k:k + n]
        sn = s - s.mean()
        ss = np.sqrt((sn ** 2).sum())
        vals[i] = (tn @ sn) / (ts * ss) if ss > 1e-9 else 0.0
    j = int(np.argmax(vals))
    peak = float(vals[j])
    mask = np.ones(len(vals), bool)
    mask[max(0, j - 15):min(len(vals), j + 16)] = False
    second = float(vals[mask].max()) if mask.any() else 0.0
    return lo + j, peak, peak / (abs(second) + 1e-9)


def best_lag(tmpl, sig, lo=None, hi=None):
    """全体のおおまかなズレ。長いので FFT ベースの相関で粗く探してから NCC で詰める"""
    if len(tmpl) >= len(sig):
        return None
    corr = np.correlate(sig, tmpl, mode="valid") / len(tmpl)
    lo = 0 if lo is None else max(0, lo)
    hi = len(corr) if hi is None else min(len(corr), hi)
    if hi <= lo:
        return None
    coarse = lo + int(np.argmax(corr[lo:hi]))
    return ncc(tmpl, sig, coarse - 30, coarse + 30)


def main(rf_video, ref_video):
    fps = fps_of(rf_video)
    a = norm(luma_series(rf_video))     # RF側（これが基準）
    b = norm(luma_series(ref_video))    # 参照側
    print(f"  RF映像  : {len(a):5d} フレーム  {fps:.3f} fps")
    print(f"  参照映像: {len(b):5d} フレーム  {fps_of(ref_video):.3f} fps")

    if len(a) >= len(b):
        print("  参照映像がRF映像より短い。同期を取れないので無補正にする")
        return dump(0.0, 0, 1.0, 0.0, "測定不能", fps)

    # --- 全体でおおまかなズレを求める ---
    r = best_lag(a, b)
    if r is None:
        return dump(0.0, 0, 1.0, 0.0, "測定不能", fps)
    lag, peak, ratio = r
    print(f"  全体の相関ピーク {peak:.3f}  2位との比 {ratio:.2f}")
    print(f"  ズレ: {lag:+d} フレーム = {lag / fps:+.3f} 秒"
          f"  （参照側のほうが {lag / fps:.1f} 秒ぶん先に始まっている）")

    # --- 前半と後半で別々に測り、その差から速度比を出す ---
    drift, note = 1.0, "前後の窓が取れないので無補正"
    seg = len(a) // 4
    if seg >= 60:                                   # 2秒ぶん以上あること
        early, late = a[:seg], a[-seg:]
        span = (len(a) - seg)                       # 2つの窓の中心間のフレーム数
        win = max(60, int(span * DRIFT_LIMIT) + 30) # 探索範囲
        re_ = ncc(early, b, lag - win, lag + win)
        rl_ = ncc(late, b, lag + span - win, lag + span + win)
        if re_ and rl_:
            d = ((rl_[0] - re_[0]) - span) / span
            print(f"  前半のズレ {re_[0]:+d}f (相関{re_[1]:.3f}) /"
                  f" 後半のズレ {rl_[0] - span:+d}f (相関{rl_[1]:.3f})")
            if min(re_[1], rl_[1]) < WINDOW_MIN_CORR:
                note = (f"窓の相関が弱い(最小{min(re_[1], rl_[1]):.3f} < "
                        f"{WINDOW_MIN_CORR})ので無補正にした")
            elif abs(d) > DRIFT_LIMIT:
                note = (f"算出値 {1 + d:.4f} は現実的な範囲(±{DRIFT_LIMIT:.0%})を"
                        f"外れているので無補正にした")
            else:
                drift, note = 1.0 + d, "前後の窓の差から算出"
    print(f"  速度比: {drift:.6f}  （{note}）")

    # --- 信頼度 ---
    if peak < 0.3:
        conf = "低い"
    elif ratio < 1.3:
        conf = "低い"          # 似た絵が多く、別の位置とも同じくらい合ってしまう
    elif peak < 0.6:
        conf = "中くらい"
    else:
        conf = "高い"
    print(f"  信頼度: {conf}")
    if conf == "低い":
        print("    ※ 映像の変化が乏しいと位置を特定しにくい。"
              "できた動画の音ズレを必ず確認すること")

    return dump(lag / fps, lag, drift, peak, conf, fps, ratio)


def dump(offset_sec, offset_frames, drift, peak, conf, fps, ratio=0.0):
    # trim_sec = 参照の先頭から切り落とす秒数。
    # 参照が先に始まっている（offset_sec > 0）なら、その分を捨てれば頭が揃う。
    # ffmpeg の -itsoffset は「遅らせる」方向なので、符号を取り違えないよう
    # 用途そのものを名前にしてある。
    json.dump({"trim_sec": offset_sec, "offset_frames": offset_frames,
               "drift": drift, "fps": fps, "peak": peak,
               "confidence": conf, "peak_ratio": ratio},
              open("/tmp/vhsalign.json", "w"))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
