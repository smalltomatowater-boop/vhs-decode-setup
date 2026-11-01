#!/usr/bin/env python3
"""cxadc から短時間サンプリングして信号の有無を判定する。
終了コード 0=信号あり / 1=無信号 / 2=読めない"""
import sys, numpy as np
TH = float(sys.argv[1]) if len(sys.argv) > 1 else 6.0
try:
    with open('/dev/cxadc0', 'rb', buffering=0) as f:
        f.read(1 << 20)                      # 先頭の過渡を捨てる
        buf = f.read(3 << 20)                # 約0.1秒ぶん
except Exception as e:
    print(f"err {e}"); sys.exit(2)
x = np.frombuffer(buf, dtype=np.uint8)
if x.size < 1000:
    print("err short"); sys.exit(2)
sd = float(x.std())
print(f"{sd:.2f}")
sys.exit(0 if sd >= TH else 1)
