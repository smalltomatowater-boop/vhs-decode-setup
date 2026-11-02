#!/usr/bin/env python3
"""標準納品版(黒点68)の品質検証。

比較する4段階（すべて 640x480 / 8bit / リミテッド符号化 に揃える）
  A  無加工      マスターをインタレース解除・切り出し・フル→リミテッド変換しただけ
  B  黒点のみ    A + 黒68→0
  C  黒点+NR     B + hqdn3d（これが納品前の処理済み映像）
  D  最終MP4     納品_標準_tape01.mp4 を復号したもの

これで
  A→B  黒レベル調整が何を失ったか
  B→C  ノイズ処理の改善と損失
  C→D  H.264符号化が何を失ったか
が分離できる。

レンジの扱い: A/B/C は out_range=tv で書き出すので、D(tvタグ付きMP4)と
同じ符号化空間になる。どちらも生のY値をそのまま比較するため、
表示ソフトによる解釈差は入らない。
"""
import csv, subprocess, sys
import numpy as np

NAS = "/Volumes/rf_tmp"
MASTER = f"{NAS}/完成_tape01.mkv"
MP4 = f"{NAS}/納品_標準_tape01.mp4"
W, H = 640, 480
BLACK = 68
SCENES = {"黒シルエット・雪原": 651.5, "黒スーツ・白壁": 653.5, "暗い室内": 630.0}
DUR = 2.0

RF = "bwdif=mode=send_field:parity=tff,crop=704:480:28:4"
GRADE = f"lutyuv=y='clip((val-{BLACK})*1023/(1023-{BLACK}),0,1023)'"
NR = "hqdn3d=2:1:4:4"
TOTV = f"scale={W}:{H}:flags=lanczos:in_range=pc:out_range=tv,setsar=1"


def read_y(src, ss, vf, dur=DUR):
    """Yプレーンを8bitで取り出す。vf の最後は必ず format=gray。"""
    out = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-ss", f"{ss}", "-i", src,
         "-t", f"{dur}", "-vf", vf, "-f", "rawvideo", "-"],
        capture_output=True).stdout
    a = np.frombuffer(out, np.uint8)
    n = len(a) // (W * H)
    if n == 0:
        raise RuntimeError(f"フレームが取れない: {src} @{ss}")
    return a[:n * W * H].reshape(n, H, W)


def runs_of(mask2d):
    """各行で True が水平方向に何画素続くかを集める"""
    out = []
    for row in mask2d:
        d = np.diff(np.concatenate(([0], row.view(np.int8), [0])))
        st = np.where(d == 1)[0]
        en = np.where(d == -1)[0]
        if len(st):
            out.extend((en - st).tolist())
    return out


def laplacian_energy(F):
    """時間平均でノイズを落としてから、残った輪郭の量を測る。
    ノイズ由来か本物の細部かを分けるため 16 コマ平均をかける。"""
    k = min(16, len(F))
    if k < 2:
        return float("nan")
    avg = np.stack([F[i:i + k].mean(0) for i in range(0, len(F) - k + 1, k)])
    lap = (4 * avg[:, 1:-1, 1:-1] - avg[:, :-2, 1:-1] - avg[:, 2:, 1:-1]
           - avg[:, 1:-1, :-2] - avg[:, 1:-1, 2:])
    return float(np.abs(lap).mean())


def measure(F):
    crushed = F <= 16
    blown = F >= 254
    r = np.array(sum((runs_of(f) for f in crushed[::6]), []) or [0])
    rb = np.array(sum((runs_of(f) for f in blown[::6]), []) or [0])
    shadow = F[(F > 16) & (F < 80)]
    high = F[(F > 200) & (F < 254)]
    return {
        "黒つぶれ率%": round(float(crushed.mean() * 100), 4),
        "つぶれのうち構造(10px以上)%": round(float(r[r >= 10].sum() / r.sum() * 100) if r.sum() else 0.0, 2),
        "白飛び率%": round(float(blown.mean() * 100), 4),
        "飛びのうち構造(10px以上)%": round(float(rb[rb >= 10].sum() / rb.sum() * 100) if rb.sum() else 0.0, 2),
        "暗部の階調数": int(len(np.unique(shadow))) if shadow.size else 0,
        "ハイライトの階調数": int(len(np.unique(high))) if high.size else 0,
        "時間ノイズ(8bit)": round(float(np.diff(F.astype(np.int16), axis=0).std() / np.sqrt(2)), 3),
        "細部(16コマ平均後)": round(laplacian_energy(F.astype(np.float32)), 4),
    }


def main():
    stages = [
        ("A 無加工",    MASTER, f"{RF},{TOTV},format=gray"),
        ("B 黒点のみ",  MASTER, f"{RF},{GRADE},{TOTV},format=gray"),
        ("C 黒点+NR",   MASTER, f"{RF},{GRADE},{NR},{TOTV},format=gray"),
        ("D 最終MP4",   MP4,    "format=gray"),
    ]
    rows = []
    for scene, t in SCENES.items():
        print(f"\n=== {scene}  （{t}秒）===")
        base = None
        for name, src, vf in stages:
            F = read_y(src, t, vf)
            m = measure(F)
            if base is None:
                base = m
            m2 = {"場面": scene, "段階": name, "フレーム数": len(F), **m}
            rows.append(m2)
            print(f"  {name:<10} つぶれ{m['黒つぶれ率%']:7.3f}% (構造{m['つぶれのうち構造(10px以上)%']:5.1f}%)"
                  f"  飛び{m['白飛び率%']:7.3f}%"
                  f"  暗部階調{m['暗部の階調数']:4d}  ハイ階調{m['ハイライトの階調数']:4d}"
                  f"  ノイズ{m['時間ノイズ(8bit)']:6.3f}  細部{m['細部(16コマ平均後)']:7.4f}")
    with open("verify.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("\n  → verify.csv に保存した")


if __name__ == "__main__":
    main()
