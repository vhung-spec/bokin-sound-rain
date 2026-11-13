#!/usr/bin/env python3
"""Đo xem một tiếng "giống gió" hay "giống lửa" đến đâu (không cần nghe).

Gió: nhiễu mịn, to nhỏ chậm (cơn giật vài giây). Lửa: nhiều tiếng nổ ngắn, dải cao "gai góc".
  kurt_hf      : độ nhọn (kurtosis) của dải 2-10 kHz. Nhiễu mịn = 3; tiếng nổ lách tách >> 3.
  hf_top5_pct  : % năng lượng dải 2-10 kHz nằm trong 5% khung 1 ms to nhất. Mịn ~ 10-15%; lửa cao.
  slow_fast_db : công suất dao động chậm (0.1-2 Hz) so với nhanh (4-40 Hz) của đường bao toàn dải, dB.
                 Gió: dương lớn (to nhỏ chậm). Lửa: thấp hơn (nhấp nháy, nổ).
  low_pct      : % năng lượng dưới 300 Hz.
Dùng: python prototypes/windiness.py file1.flac file2.mp3 ...   (hoặc import measure())
"""
import subprocess
import sys

import numpy as np

SR = 48000


def _bandpass(x, lo, hi):
    f = np.fft.rfftfreq(x.size, 1 / SR)
    X = np.fft.rfft(x)
    X[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(X, n=x.size)


def measure(y):
    """y: (2, n) or (n,) float array at 48 kHz."""
    m = y.mean(axis=0) if y.ndim == 2 else y
    hf = _bandpass(m, 2000, 10000)
    kurt = float(np.mean(hf ** 4) / np.mean(hf ** 2) ** 2)
    fr = SR // 1000
    e = np.sum(hf[: hf.size // fr * fr].reshape(-1, fr) ** 2, axis=1)
    top = np.sort(e)[::-1][: max(1, e.size // 20)].sum() / e.sum()
    fr10 = SR // 100  # 10 ms envelope
    env = np.sqrt(np.mean(m[: m.size // fr10 * fr10].reshape(-1, fr10) ** 2, axis=1))
    env = np.log(env + 1e-9)
    env -= env.mean()
    f = np.fft.rfftfreq(env.size, 0.01)
    P = np.abs(np.fft.rfft(env)) ** 2
    slow = P[(f >= 0.1) & (f < 2)].sum()
    fast = P[(f >= 4) & (f < 40)].sum()
    fa = np.fft.rfftfreq(m.size, 1 / SR)
    Pa = np.abs(np.fft.rfft(m)) ** 2
    return {"kurt_hf": round(kurt, 1), "hf_top5_pct": round(100 * float(top), 1),
            "slow_fast_db": round(10 * np.log10(slow / fast), 1),
            "low_pct": round(100 * float(Pa[(fa > 20) & (fa < 300)].sum() / Pa[fa > 20].sum()), 1)}


def load(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, "<f4").reshape(-1, 2).T


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(p, measure(load(p)))
