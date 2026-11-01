#!/usr/bin/env python3
"""RF復号映像と参照キャプチャ映像を突き合わせて、ズレ(秒)と速度比を求める。
輝度の時間変化を相互相関にかけてフレーム単位のオフセットを出し、
再生時間の比からクロックドリフトを推定する。"""
import subprocess, sys, json, numpy as np

W, H = 32, 24

def luma_series(path):
    """1フレームあたりの平均輝度の時系列を返す"""
    cmd = ["ffmpeg", "-v", "error", "-i", path,
           "-vf", f"scale={W}:{H},format=gray", "-f", "rawvideo", "-"]
    p = subprocess.run(cmd, capture_output=True)
    buf = np.frombuffer(p.stdout, dtype=np.uint8)
    n = len(buf) // (W * H)
    if n == 0:
        raise RuntimeError(f"フレームを読めません: {path}")
    return buf[:n * W * H].reshape(n, W * H).mean(axis=1).astype(np.float64)

def fps_of(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                          "-show_entries", "stream=r_frame_rate",
                          "-of", "default=nw=1:nk=1", path],
                         capture_output=True, text=True).stdout.strip()
    a, b = (out.split("/") + ["1"])[:2]
    return float(a) / float(b)

def dur_of(path, stream):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", stream,
                          "-show_entries", "stream=duration",
                          "-of", "default=nw=1:nk=1", path],
                         capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                              "format=duration", "-of", "default=nw=1:nk=1", path],
                             capture_output=True, text=True).stdout.strip()
        return float(out)

def main(rf_video, ref_video):
    fps = fps_of(rf_video)
    a = luma_series(rf_video)
    b = luma_series(ref_video)
    print(f"  RF映像  : {len(a):5d} フレーム  {fps:.3f} fps")
    print(f"  参照映像: {len(b):5d} フレーム  {fps_of(ref_video):.3f} fps")

    # 平均を抜いて正規化（明るさの違いを吸収）
    an = (a - a.mean()) / (a.std() + 1e-9)
    bn = (b - b.mean()) / (b.std() + 1e-9)
    # 短いほうをテンプレートにして相互相関
    if len(an) <= len(bn):
        tmpl, sig, sign = an, bn, +1
    else:
        tmpl, sig, sign = bn, an, -1
    corr = np.correlate(sig, tmpl, mode="valid") / len(tmpl)
    lag = int(np.argmax(corr))
    peak = float(corr[lag])
    # 2番目に高いピークと比べて信頼度を見る
    mask = np.ones(len(corr), bool)
    lo, hi = max(0, lag - 15), min(len(corr), lag + 16)
    mask[lo:hi] = False
    second = float(corr[mask].max()) if mask.any() else 0.0
    ratio = peak / (abs(second) + 1e-9)

    offset_frames = sign * lag
    offset_sec = offset_frames / fps
    drift = dur_of(ref_video, "a:0") / max(dur_of(rf_video, "v:0"), 1e-9)

    print(f"  相関ピーク: {peak:.3f}  （2位 {second:.3f} / 比 {ratio:.2f}）")
    if peak < 0.3 or ratio < 1.5:
        conf = "低い"
    elif peak < 0.6:
        conf = "中くらい"
    else:
        conf = "高い"
    print(f"  信頼度   : {conf}")
    print(f"  ズレ     : {offset_frames:+d} フレーム = {offset_sec:+.3f} 秒")
    print(f"  速度比   : {drift:.6f}  （1.0から離れるほどクロックがずれている）")

    json.dump({"offset_sec": offset_sec, "offset_frames": offset_frames,
               "drift": drift, "fps": fps, "peak": peak,
               "confidence": conf, "peak_ratio": ratio},
              open("/tmp/vhsalign.json", "w"))

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
