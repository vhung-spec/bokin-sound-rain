#!/usr/bin/env python3
"""Bản thử nghiệm: tổng hợp tiếng lửa bằng thuật toán (lửa trại, lò sưởi, củi lách tách).

Chỉ là prototype để đánh giá hướng thuật toán; KHÔNG sửa rain.py, chỉ dùng lại vài hàm của nó
(ShapedNoise, Swell, band, widen, loudness_lufs, finish, FFmpegSink).

Mô hình gồm 6 thành phần, tất cả cùng đi theo một biến "sức lửa" (intensity) dao động chậm:
  1. roar   - tiếng gầm/ù trầm của sự cháy: nhiễu 25-300 Hz, to nhỏ theo sức lửa.
  2. lap    - tiếng lửa liếm "phập phù": nhiễu dải giữa 150-2000 Hz nhân với đường bao
              nhấp nháy 2-12 Hz đã chỉnh lưu (như "lapping" của Farnell: nhiễu trầm bị cắt/chỉnh lưu).
  3. crackle- tiếng nổ lách tách: quá trình điểm tự kích thích (Hawkes) -> nổ theo chùm;
              biên độ phân bố Pareto (nhiều tiếng tí tách nhỏ, ít tiếng "đốp" to);
              mỗi tiếng nổ là một xung nhiễu ngắn 0.3-15 ms qua bộ cộng hưởng 1.2-9 kHz,
              tiếng to có thêm "thân" trầm 250-1200 Hz.
  4. hiss   - tiếng xì của khí/hơi nước: nhiễu 1.5-12 kHz, đường bao thưa (exp của AR) nên lúc có lúc không.
  5. whistle- tiếng rít của nhựa/hơi nước phụt ra: âm hẹp 2-7 kHz, cao độ trôi, 0.5-6 s, hiếm.
  6. collapse - củi đổ/sụp: tiếng "thụp" trầm + tiếng cọ gỗ + một tràng lách tách + lửa bùng lên.
Lò sưởi (fireplace) thêm phản xạ phòng nhỏ bằng IR tổng hợp.

Ví dụ:
  python prototypes/fire_proto.py render -p campfire -d 30s -s 1 -o fire.flac
  python prototypes/fire_proto.py demo --outdir prototypes/out      # 4 preset x 30 s + số đo + spectrogram
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import rain  # noqa: E402

SR = rain.SAMPLE_RATE
CHUNK = int(rain.CHUNK_SECONDS * SR)


@dataclass(frozen=True)
class FireParams:
    # roar: tiếng gầm trầm
    roar_level: float = 0.5
    roar_high_hz: float = 220.0
    # lap: lửa liếm phập phù
    lap_level: float = 0.25
    lap_low_hz: float = 180.0
    lap_high_hz: float = 1800.0
    lap_flicker_hz: float = 6.0  # tốc độ nhấp nháy của ngọn lửa
    lap_depth: float = 0.6  # 0 = đều, 1 = phập phù mạnh
    # crackle: tiếng nổ lách tách
    crackle_rate: float = 4.0  # số "tiếng nổ gốc" mỗi giây (chưa tính tiếng con trong chùm)
    crackle_branch: float = 0.55  # mỗi tiếng nổ sinh trung bình bấy nhiêu tiếng con (<1)
    crackle_cluster_ms: float = 45.0  # khoảng cách trung bình giữa các tiếng trong một chùm
    crackle_alpha: float = 1.6  # số mũ Pareto của biên độ: nhỏ hơn = nhiều tiếng "đốp" to hơn
    crackle_level: float = 0.6  # độ lớn tiếng nổ điển hình (tương đối so với nền)
    crackle_low_hz: float = 1200.0
    crackle_high_hz: float = 9000.0
    pop_share: float = 0.15  # tỉ lệ tiếng nổ to có "thân" trầm
    # hiss + whistle
    hiss_level: float = 0.12
    hiss_sparsity: float = 0.6  # 0 = xì đều, lớn hơn = từng cơn
    whistle_per_min: float = 0.6
    whistle_level: float = 0.08
    # collapse: củi sụp
    collapse_per_min: float = 0.25
    collapse_level: float = 1.0
    # tổng thể
    intensity_db: float = 3.0  # sức lửa lên xuống bao nhiêu dB
    intensity_seconds: float = 40.0
    width: float = 0.8
    room: float = 0.0  # 0 = ngoài trời, 1 = phòng nhỏ (lò sưởi)
    room_rt60: float = 0.45


PRESETS: dict[str, tuple[str, FireParams]] = {
    "campfire": ("Lửa trại ngoài trời: gầm ấm, lách tách vừa, thỉnh thoảng củi sụp", FireParams()),
    "fireplace": ("Lò sưởi trong phòng: êm hơn, có tiếng vang phòng, ít gầm", FireParams(
        roar_level=0.35, roar_high_hz=180, lap_level=0.25, lap_flicker_hz=4.5, crackle_rate=3.0,
        crackle_level=0.5, crackle_high_hz=7500, hiss_level=0.08, whistle_per_min=0.4,
        collapse_per_min=0.15, width=0.6, room=0.6, room_rt60=0.5)),
    "crackling": ("Củi khô cháy lách tách dày (kiểu ASMR)", FireParams(
        roar_level=0.25, lap_level=0.2, crackle_rate=9.0, crackle_branch=0.65, crackle_alpha=1.4,
        crackle_level=0.75, pop_share=0.2, hiss_level=0.06, collapse_per_min=0.2)),
    "embers": ("Than hồng sắp tàn: rất êm, tí tách thưa, nhiều tiếng xì", FireParams(
        roar_level=0.25, roar_high_hz=150, lap_level=0.08, lap_depth=0.5, crackle_rate=1.2,
        crackle_branch=0.4, crackle_alpha=2.2, crackle_level=0.35, pop_share=0.05, hiss_level=0.08,
        hiss_sparsity=1.2, whistle_per_min=1.2, whistle_level=0.06, collapse_per_min=0.08,
        collapse_level=0.5, intensity_db=2.0)),
}


def vary(p: FireParams, variation: float, rng) -> FireParams:
    """Nudge every numeric field by up to about +-variation (log scale), same count of draws always."""
    names = [f.name for f in fields(p)]
    u = rng.uniform(-1.0, 1.0, len(names))
    if variation <= 0:
        return p
    out = {}
    for name, x in zip(names, u):
        v = getattr(p, name)
        if name in ("room", "width", "lap_depth"):
            out[name] = float(np.clip(v + 0.5 * variation * x, 0.0, 1.0)) if v > 0 else v
        elif name == "crackle_branch":
            out[name] = float(np.clip(v * math.exp(0.5 * variation * x), 0.0, 0.85))
        else:
            out[name] = v * math.exp(variation * x)
    return replace(p, **out)


# ------------------------------------------------------------------ helpers

def _fft_filter(x, sr, mag_fn):
    n = x.shape[-1]
    f = np.maximum(np.fft.rfftfreq(n, 1.0 / sr), 1.0)
    return np.fft.irfft(np.fft.rfft(x, axis=-1) * mag_fn(f), n=n, axis=-1)


def _pan(mono, angle):
    return np.stack([mono * math.cos(angle), mono * math.sin(angle)])


class Control:
    """Smooth random control signal at 200 Hz, AR(1) with given time constant, unit variance."""

    def __init__(self, rng, tau, rate=200):
        self.rng, self.rate, self.c = rng, rate, math.exp(-1.0 / (rate * tau))
        self.k = math.sqrt(1 - self.c * self.c)
        self.state = rng.standard_normal()
        self.last = self.state
        self.buf = np.zeros(0)

    def read(self, n, sr=SR):
        step = sr // self.rate
        missing = n - self.buf.size
        if missing > 0:
            m = -(-missing // step)
            noise = self.rng.standard_normal(m)
            vals = np.empty(m + 1)
            vals[0] = s = self.last
            for i, e in enumerate(noise.tolist(), 1):
                s = self.c * s + self.k * e
                vals[i] = s
            self.last = s
            self.buf = np.concatenate([self.buf, np.interp(np.arange(m * step) / step, np.arange(m + 1), vals)])
        out, self.buf = self.buf[:n], self.buf[n:]
        return out


class Overlay:
    """Places finished stereo kernels at absolute sample positions across chunk boundaries."""

    def __init__(self):
        self.pending: list[tuple[int, np.ndarray]] = []
        self.pos = 0

    def add(self, at, wave):
        self.pending.append((int(at), wave))

    def read(self, n):
        out = np.zeros((2, n), np.float32)
        keep = []
        for at, w in self.pending:
            a = at - self.pos
            lo, hi = max(0, a), min(n, a + w.shape[1])
            if hi > lo:
                out[:, lo:hi] += w[:, lo - a : hi - a]
            if a + w.shape[1] > n:
                keep.append((at, w))
        self.pending = keep
        self.pos += n
        return out


# ------------------------------------------------------------------ sound kernels

def crackle_kernel(rng, p: FireParams, big: bool):
    """One crackle: short noise burst through 1-2 resonances; big ones get a low 'body'."""
    dur = rng.uniform(0.004, 0.015) if big else math.exp(rng.uniform(math.log(0.0003), math.log(0.006)))
    n = int(SR * (dur * 7 + 0.003))
    t = np.arange(n) / SR
    burst = rng.standard_normal(n) * np.exp(-t / dur)
    if rng.random() < 0.3:  # some crackles stutter: 2-4 micro-impulses in a few ms
        for _ in range(int(rng.integers(1, 4))):
            d = min(int(rng.uniform(0.0005, 0.006) * SR), n - 1)
            burst[d:] += rng.standard_normal(n - d) * np.exp(-t[: n - d] / (dur * 0.5)) * rng.uniform(0.3, 0.9)
    f1 = math.exp(rng.uniform(math.log(p.crackle_low_hz), math.log(p.crackle_high_hz)))
    q1 = rng.uniform(1.5, 8.0)
    f2 = f1 * rng.uniform(1.3, 2.4)
    g2 = rng.uniform(0.0, 0.7)
    y = _fft_filter(burst, SR, lambda f: (rain._resonance(f, f1, q1) + g2 * rain._resonance(f, f2, q1))
                    * rain.band(f, 400.0, 16000.0, 0.0, 2, 2))
    if big:  # wood/gas pocket body
        fb = rng.uniform(250, 1200)
        tb = rng.uniform(0.003, 0.012)
        body = np.sin(2 * np.pi * fb * t + rng.uniform(0, 6.28)) * np.exp(-t / tb) * (1 - np.exp(-t / 0.0004))
        y = y / (np.max(np.abs(y)) + 1e-9) + body * rng.uniform(0.3, 0.8)
    return rain._trim(y, 1e-3)


def whistle_wave(rng, sr=SR):
    """Resin/steam jet: narrow-band tone with drifting pitch, flutter and a breathy edge."""
    dur = rng.uniform(0.6, 6.0)
    n = int(dur * sr)
    t = np.arange(n) / sr
    f0 = math.exp(rng.uniform(math.log(2000), math.log(7000)))
    drift = np.cumsum(rng.standard_normal(n // 480 + 2))[: n // 480 + 2]
    drift = np.interp(t * 100, np.arange(drift.size), drift)
    freq = f0 * (1 + 0.004 * drift + rng.uniform(-0.15, 0.1) * t / dur)
    tone = np.sin(2 * np.pi * np.cumsum(freq) / sr)
    flutter = 1 + 0.5 * np.interp(t * 30, np.arange(int(dur * 30) + 2), rng.standard_normal(int(dur * 30) + 2))
    breath = _fft_filter(rng.standard_normal(n), sr, lambda f: rain._resonance(f, f0, 12.0))
    breath /= np.std(breath) + 1e-9
    env = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** rng.uniform(0.5, 2.0)
    y = (tone * rng.uniform(0.2, 0.7) + breath * 0.5) * np.clip(flutter, 0, None) * env
    return _pan(y / (np.max(np.abs(y)) + 1e-9), rng.uniform(0.25, 1.3)).astype(np.float32)


def collapse_wave(rng, sr=SR):
    """Logs settling: a low thump, a short wooden scrape and a sprinkle of embers."""
    n = int(sr * 2.5)
    t = np.arange(n) / sr
    thump = _fft_filter(rng.standard_normal(n), sr, lambda f: rain.band(f, 40, 220, 0, 2, 3))
    thump = thump / (np.std(thump[: sr // 5]) + 1e-9) * np.exp(-t / rng.uniform(0.08, 0.25)) * (1 - np.exp(-t / 0.003))
    scrape_len = rng.uniform(0.2, 0.9)
    tt = np.clip(t - rng.uniform(0.0, 0.08), 0, None)
    grain = rng.standard_normal(n) * (rng.random(n) < 0.08)
    scrape = _fft_filter(grain, sr, lambda f: rain.band(f, 300, 3500, 0.3))
    scrape = scrape / (np.std(scrape) + 1e-9) * np.exp(-tt / scrape_len) * (tt > 0)
    y = thump * 1.0 + scrape * rng.uniform(0.15, 0.4)
    return _pan(y / (np.max(np.abs(y)) + 1e-9), rng.uniform(0.4, 1.17)).astype(np.float32)


def room_ir(rng, rt60, sr=SR):
    """Small-room impulse response: a few early reflections and an exponentially decaying noise tail."""
    n = int(sr * rt60 * 1.2)
    t = np.arange(n) / sr
    tail = rng.standard_normal((2, n)) * np.exp(-6.9 * t / rt60) * (t > 0.012)
    tail = _fft_filter(tail, sr, lambda f: rain.band(f, 80, 5000, 0.4))
    ir = tail / np.sqrt(np.sum(tail ** 2, axis=1, keepdims=True))
    for _ in range(6):
        d = int(rng.uniform(0.003, 0.02) * sr)
        ir[:, d] += rng.uniform(0.1, 0.35) * rng.choice([-1, 1], 2)
    return ir.astype(np.float32)


# ------------------------------------------------------------------ the synth

class FireSynth:
    def __init__(self, p: FireParams, seed: int):
        r = [np.random.default_rng([seed, 1000 + i]) for i in range(10)]
        self.p, self.r = p, r
        self.roar = rain.ShapedNoise(r[0], SR, lambda f: rain.band(f, 25.0, p.roar_high_hz, 0.6, 2, 3))
        self.lap = rain.ShapedNoise(r[1], SR, lambda f: rain.band(f, p.lap_low_hz, p.lap_high_hz, 0.5))
        self.hiss = rain.ShapedNoise(r[2], SR, lambda f: rain.band(f, 2000.0, 9000.0, 0.2, 2, 4))
        self.flicker = [Control(r[3], 1.0 / (2 * math.pi * p.lap_flicker_hz)) for _ in range(2)]
        self.hiss_env = Control(r[4], 0.6)
        self.intensity = rain.Swell(r[5], SR, p.intensity_db, p.intensity_seconds)
        self.events = Overlay()
        self.crng = r[6]
        self.bank_small = [crackle_kernel(r[6], p, False) for _ in range(64)]
        self.bank_big = [crackle_kernel(r[6], p, True) for _ in range(24)]
        self.erng = r[7]
        self.boost = 0.0  # extra crackle/roar after a collapse, decays
        self.boost_tau = 8.0
        self.pos = 0
        self.conv = None
        if p.room > 0:
            ir = room_ir(r[8], p.room_rt60)
            irs = np.zeros((2, 2, ir.shape[1]), np.float32)
            irs[0, 0], irs[1, 1] = ir[0], ir[1]
            self.conv = rain.Convolver(irs, CHUNK)
        self.crackle_log: list[float] = []  # (for analysis) amplitude of every crackle placed

    # crackles ------------------------------------------------------
    def _crackles(self, n, rate_gain):
        p, rng = self.p, self.crng
        out = np.zeros((2, n), np.float32)
        lam = p.crackle_rate * rate_gain
        peak = float(lam.max())
        cnt = int(rng.poisson(peak * n / SR))
        parents = rng.integers(0, n, cnt)
        parents = parents[rng.random(cnt) < lam[parents] / max(peak, 1e-9)]
        times, amps = [], []
        for s in parents.tolist():
            # Pareto amplitude (min 1), clipped at 8x (~18 dB)
            a = min(rng.random() ** (-1.0 / p.crackle_alpha), 8.0)
            times.append(s)
            amps.append(a)
            # self-exciting cluster: chain of children with decreasing amplitude
            k = rng.poisson(p.crackle_branch / max(1 - p.crackle_branch, 0.05))
            t = s
            for _ in range(int(k)):
                t += int(rng.exponential(p.crackle_cluster_ms / 1000) * SR) + int(0.0015 * SR)
                times.append(t)
                amps.append(min(rng.random() ** (-1.0 / p.crackle_alpha), 8.0) * rng.uniform(0.3, 0.9))
        base = p.crackle_level * 2.0  # bed RMS is ~0.5-0.7 before calibration: small ticks ~6 dB over it
        for t, a in zip(times, amps):
            big = a > 2.5 and rng.random() < min(1.0, p.pop_share * 4)
            bank = self.bank_big if big else self.bank_small
            k = bank[int(rng.integers(len(bank)))]
            # brighter and closer when louder; pan near the fire centre
            angle = (rng.uniform(-1, 1) * p.width * 0.8 + 1) * math.pi / 4
            self.events.add(self.pos + t, _pan(k * (base * a), angle).astype(np.float32))
            self.crackle_log.append(a)
        # slowly refresh banks so long renders don't repeat
        self.bank_small[int(rng.integers(64))] = crackle_kernel(rng, p, False)
        if rng.random() < 0.3:
            self.bank_big[int(rng.integers(24))] = crackle_kernel(rng, p, True)
        return out

    # rare events ---------------------------------------------------
    def _rare(self, n):
        p, rng = self.p, self.erng
        sec = n / SR
        for _ in range(rng.poisson(p.whistle_per_min / 60 * sec)):
            w = whistle_wave(rng) * np.float32(p.whistle_level)
            self.events.add(self.pos + int(rng.integers(n)), w)
        for _ in range(rng.poisson(p.collapse_per_min / 60 * sec)):
            at = int(rng.integers(n))
            w = collapse_wave(rng) * np.float32(0.25 * p.collapse_level)
            self.events.add(self.pos + at, w)
            self.boost += rng.uniform(1.5, 4.0) * p.collapse_level
            self.boost_tau = rng.uniform(4.0, 15.0)

    def read(self, n):
        p = self.p
        t = np.arange(n) / SR
        boost = self.boost * np.exp(-t / self.boost_tau)
        self.boost = float(boost[-1] * math.exp(-1 / SR / self.boost_tau)) if n else self.boost
        inten = self.intensity.read(n) * (1 + 0.15 * boost)
        roar = rain.widen(self.roar.read(n), p.width * 0.5) * (p.roar_level * np.sqrt(inten))
        fl = np.stack([c.read(n) for c in self.flicker])
        # rectified flicker: flames "puff" rather than wobble symmetrically
        env = np.maximum(0.0, 0.4 + fl) ** 2
        env = (1 - p.lap_depth) + p.lap_depth * env / 0.8
        lap = rain.widen(self.lap.read(n), p.width) * env * (p.lap_level * inten)
        h = np.exp(p.hiss_sparsity * self.hiss_env.read(n) - p.hiss_sparsity ** 2 / 2)
        hiss = rain.widen(self.hiss.read(n), p.width) * (p.hiss_level * h)
        self._rare(n)
        self._crackles(n, inten ** 2 * (1 + boost))
        y = (roar + lap + hiss).astype(np.float32) + self.events.read(n)
        self.pos += n
        if self.conv is not None:
            y = y + self.conv.process(y) * np.float32(p.room * 0.5)
        return y.astype(np.float32)


def fire_chunks(p: FireParams, seed: int, total: int, loudness=-20.0):
    synth = FireSynth(p, seed)
    first = []
    done = 0
    while done < total and done < rain.CALIBRATION_SECONDS * SR:
        m = min(CHUNK, total - done)
        first.append(synth.read(m))
        done += m
    gain = np.float32(10 ** ((loudness - rain.loudness_lufs(np.concatenate(first, axis=1), SR)) / 20))
    for c in first:
        yield c * gain
    while done < total:
        m = min(CHUNK, total - done)
        yield synth.read(m) * gain
        done += m
    synth_stats.update(crackles=len(synth.crackle_log))


synth_stats: dict = {}


def render(preset, seed, seconds, out: Path, variation=0.15, loudness=-20.0):
    rng = np.random.default_rng([seed, 999])
    p = vary(PRESETS[preset][1], variation, rng)
    total = int(seconds * SR)
    sink = rain.FFmpegSink(out)
    buf = []

    def write(y):
        buf.append(y)
        sink.write(y)

    rain.finish(fire_chunks(p, seed, total, loudness), total, write, SR, fade=1.0)
    sink.close()
    return p, np.concatenate(buf, axis=1)


# ------------------------------------------------------------------ analysis

def analyse(y, sr=SR):
    """Numbers to sanity-check a render without listening."""
    mono = y.mean(axis=0)
    lufs = rain.loudness_lufs(y, sr)
    peak = float(np.max(np.abs(y)))
    # transient detector: high-passed (>1 kHz) envelope in 1 ms frames vs. local median
    hp = _fft_filter(mono, sr, lambda f: 1 / np.sqrt(1 + (1000 / f) ** 8))
    fr = sr // 1000
    e = np.sqrt(np.mean(hp[: hp.size // fr * fr].reshape(-1, fr) ** 2, axis=1))
    k = 50
    pad = np.pad(e, k, mode="edge")
    med = np.median(np.lib.stride_tricks.sliding_window_view(pad, 2 * k + 1)[:: 1], axis=1)[: e.size]
    hot = e > 4 * med + 1e-6
    onsets = np.flatnonzero(hot[1:] & ~hot[:-1]) + 1
    onsets = onsets[np.insert(np.diff(onsets) > 3, 0, True)] if onsets.size else onsets
    dur = y.shape[1] / sr
    gaps = np.diff(onsets) / 1000.0
    cv = float(np.std(gaps) / np.mean(gaps)) if gaps.size > 2 else float("nan")
    # spectrum: energy share per band
    f = np.fft.rfftfreq(mono.size, 1 / sr)
    P = np.abs(np.fft.rfft(mono)) ** 2
    bands = [(20, 200), (200, 1000), (1000, 4000), (4000, 12000), (12000, 24000)]
    tot = P[(f >= 20)].sum()
    share = {f"{a}-{b} Hz": round(float(P[(f >= a) & (f < b)].sum() / tot * 100), 1) for a, b in bands}
    centroid = float((f * P).sum() / P.sum())
    # short-term (400 ms) loudness range as a "liveliness" proxy
    w = int(0.4 * sr)
    st = [rain.loudness_lufs(y[:, i : i + w], sr) for i in range(0, y.shape[1] - w, w)]
    return {
        "lufs": round(lufs, 2),
        "peak_dbfs": round(20 * math.log10(peak + 1e-12), 2),
        "softclip_samples_pct": round(float(np.mean(np.abs(y) > 0.7) * 100), 4),
        "crest_db": round(20 * math.log10(peak / (np.sqrt(np.mean(y ** 2)) + 1e-12)), 1),
        "transients_per_s": round(onsets.size / dur, 2),
        "gap_cv": round(cv, 2),  # 1 = Poisson, >1 = bursty/clustered
        "spectral_centroid_hz": round(centroid),
        "energy_share_pct": share,
        "short_term_lufs_p10_p90": [round(float(np.percentile(st, 10)), 1), round(float(np.percentile(st, 90)), 1)],
    }


def spectrogram(audio: Path, png: Path):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(audio), "-lavfi",
                    "showspectrumpic=s=1200x500:mode=combined:scale=log:fscale=lin:legend=1", str(png)],
                   check=True)
    # zoom on 2 seconds to show individual crackles
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "10", "-t", "2", "-i", str(audio),
                    "-lavfi", "showspectrumpic=s=1200x500:mode=combined:scale=log:legend=1",
                    str(png.with_name(png.stem + "_zoom2s.png"))], check=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "10", "-t", "2", "-i", str(audio),
                    "-lavfi", "showwavespic=s=1200x300:split_channels=1",
                    str(png.with_name(png.stem + "_wave2s.png"))], check=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("-p", "--preset", default="campfire", choices=list(PRESETS))
    r.add_argument("-d", "--duration", default="30s")
    r.add_argument("-s", "--seed", type=int, default=1)
    r.add_argument("-v", "--variation", type=float, default=0.15)
    r.add_argument("--loudness", type=float, default=-20.0)
    r.add_argument("-o", "--output", default="fire.flac")
    d = sub.add_parser("demo")
    d.add_argument("--outdir", default="prototypes/out")
    d.add_argument("-d", "--duration", default="30s")
    d.add_argument("-s", "--seed", type=int, default=1)
    a = ap.parse_args(argv)
    if a.cmd == "render":
        p, y = render(a.preset, a.seed, rain.parse_duration(a.duration), Path(a.output), a.variation, a.loudness)
        print(json.dumps(analyse(y), ensure_ascii=False, indent=1))
        return
    out = Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)
    report = {}
    for i, name in enumerate(PRESETS):
        f = out / f"fire_{name}_seed{a.seed + i}.flac"
        p, y = render(name, a.seed + i, rain.parse_duration(a.duration), f)
        m = analyse(y)
        m["crackles_placed"] = synth_stats.get("crackles")
        m["params"] = asdict(p)
        report[f.name] = m
        spectrogram(f, f.with_suffix(".png"))
        print(f.name, {k: v for k, v in m.items() if k != "params"})
    (out / "metrics.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
