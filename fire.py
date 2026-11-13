#!/usr/bin/env python3
"""Tiếng lửa: tổng hợp bằng thuật toán, trộn thêm một chút bản thu thật.

Lớp chính là tiếng lửa tổng hợp (gầm trầm, lửa liếm phập phù, lách tách theo chùm, tiếng xì,
tiếng rít nhựa cây, củi sụp). Mỗi seed ra một bản khác. Nếu có bản thu lửa thật trong
library/<thư mục>, một đoạn ngẫu nhiên của chúng được cắt ghép (crossfade) và trộn nhỏ bên dưới
để thêm "chất" thật; seed khác thì đoạn khác.

Ví dụ:
  python fire.py presets
  python fire.py render -p fireplace -d 10m -o lo_suoi.flac                  # chỉ tổng hợp
  python fire.py render -p campfire --real lua -d 10m -o lua_trai.flac       # + bản thu trong library/lua
  python fire.py batch -p campfire,fireplace --real lua -n 20 -d 1h --outdir output -j 4
  python fire.py video videos/ --real lua -p fireplace --outdir output
"""
from __future__ import annotations

import argparse
import itertools
import math
import shutil
import sys
import time
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

import numpy as np

import rain
import rainmix

SR = rain.SAMPLE_RATE
CHUNK = int(rain.CHUNK_SECONDS * SR)
LAYER_REFERENCE = rainmix.LAYER_REFERENCE  # both layers are brought to this loudness before mixing
CALIBRATION_SECONDS = 60.0  # longer than rain.py: sparse crackles, whistles and collapses vary more


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
                    * rain.band(f, 400.0, 14000.0, 0.0, 2, 4))
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



def synth_chunks(p: FireParams, seed: int, total: int, loudness=LAYER_REFERENCE):
    """Yield (2, n) chunks of synthesized fire, calibrated on the first seconds to `loudness` LUFS."""
    synth = FireSynth(p, seed)
    first, done = [], 0
    while done < total and done < CALIBRATION_SECONDS * SR:
        m = min(CHUNK, total - done)
        first.append(synth.read(m))
        done += m
    gain = np.float32(10 ** ((loudness - rain.loudness_lufs(np.concatenate(first, axis=1), SR)) / 20))
    yield from (c * gain for c in first)
    while done < total:
        m = min(CHUNK, total - done)
        yield synth.read(m) * gain
        done += m


def pick_params(presets: list[str], variation: float, seed: int) -> tuple[str, FireParams]:
    rng = np.random.default_rng([seed, 999])
    name = presets[int(rng.integers(len(presets)))]
    return name, vary(PRESETS[name][1], variation, rng)


# ------------------------------------------------------------------ real recordings

def real_files(library_dir: str, folder: str) -> tuple[rainmix.Library, list[str]]:
    """Measure the recordings once (cached in the library) and return the usable ones."""
    library = rainmix.Library(library_dir)
    files = library.files(folder)
    if not files:
        raise SystemExit(f"Không có file âm thanh trong {Path(library_dir) / folder}")
    good, bad = library.usable(files)
    if bad:
        print(f"Bỏ qua file không đọc được: {', '.join(bad)}", file=sys.stderr)
    library.save()
    good = [f for f in good if library.info(f)["duration"] >= 0.5]
    if not good:
        raise SystemExit(f"Không có file đủ dài trong {Path(library_dir) / folder}")
    return library, good


class RealBed:
    """Random stretches of the real recordings joined with crossfades, with a slow swell.

    Per seed the playback speed differs by up to about ±3% and the low cut by ±20%, so even a
    single recording gives renders that do not line up with each other.
    """

    def __init__(self, library, files, folder, seed, variation):
        rng = np.random.default_rng([seed, 2000])
        u = rng.uniform(-1.0, 1.0, 2)
        layer = rainmix.Layer(name="Lửa (bản thu)", source=folder, highpass_hz=30.0 * math.exp(variation * u[0]),
                              speed=math.exp(0.2 * variation * u[1]))
        self.bed = rainmix.BedFromFiles(rng, library, files, layer, SR)
        self.swell = rain.Swell(rng, SR, 2.0, 30.0)
        self.speed = layer.speed

    def read(self, n):
        return self.bed.read(n) * self.swell.read(n).astype(np.float32)


def fire_chunks(p, seed, total, loudness=-20.0, real=None, real_db=-6.0, variation=0.15):
    """The full mix: synthesized fire plus (optionally) real recordings `real_db` dB below it."""
    synth = synth_chunks(p, seed, total)
    bed = RealBed(*real, seed, variation) if real else None
    real_gain = np.float32(10 ** (real_db / 20))

    def mixed():
        for chunk in synth:
            yield chunk + bed.read(chunk.shape[1]) * real_gain if bed else chunk

    stream = mixed()
    first, count = [], 0
    for c in stream:
        first.append(c)
        count += c.shape[1]
        if count >= min(total, CALIBRATION_SECONDS * SR):
            break
    gain = np.float32(10 ** ((loudness - rain.loudness_lufs(np.concatenate(first, axis=1), SR)) / 20))
    # The loudest crackles are turned down smoothly (not clipped, which would add harsh
    # overtones and overshoot between samples), so lossy encoders such as AAC keep headroom.
    yield from limit((c * gain for c in itertools.chain(first, stream)), total)


def limit(chunks, total, ceiling=0.68, look=48):
    """Look-ahead peak limiter: gain = ceiling / (max |x| within ±look samples), smoothed.

    The smoothing window is narrower than the max window, so the smoothed gain still keeps
    every sample under the ceiling. Output has the same length as the input.
    """
    width = 2 * look + 1
    history = np.zeros((2, 2 * look), np.float32)  # input before the current block (left context)
    pending = None

    def process(block, right):
        z = np.concatenate([history, block, right], axis=1)
        a = np.abs(z).max(axis=0)
        peak = np.lib.stride_tricks.sliding_window_view(a, width).max(axis=1)  # centred on z[look:-look]
        g = np.minimum(1.0, ceiling / np.maximum(peak, 1e-9))
        g = np.convolve(g, np.ones(look + 1) / (look + 1), mode="valid")  # centred on z[2look - look/2 ...]
        start = 2 * look - look - look // 2
        return block * g[start : start + block.shape[1]].astype(np.float32)

    for chunk in chunks:
        if pending is not None:
            right = chunk[:, : 2 * look]
            if right.shape[1] < 2 * look:
                right = np.pad(right, ((0, 0), (0, 2 * look - right.shape[1])))
            out = process(pending, right)
            history = np.concatenate([history, pending], axis=1)[:, -2 * look :]
            yield out
        pending = chunk
    if pending is not None:
        yield process(pending, np.zeros((2, 2 * look), np.float32))


# ------------------------------------------------------------------ jobs and command line

def run_job(job: dict) -> dict:
    """Render one output file. Top-level so it can run in a worker process."""
    started = time.time()
    preset, params = pick_params(job["presets"], job["variation"], job["seed"])
    out = Path(job["output"])
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".part" + out.suffix)
    video = Path(job["video"]) if job.get("video") else None
    real = None
    if job.get("real"):
        library, files = real_files(job["library"], job["real"])
        real = (library, files, job["real"])
    total = int(round(job["seconds"] * SR))
    sink = rain.FFmpegSink(tmp, video=video)
    try:
        rain.finish(fire_chunks(params, job["seed"], total, job["loudness"], real, job["real_db"], job["variation"]),
                    total, sink.write, SR, job["fade"], job.get("progress"))
        sink.close()
    except BaseException:
        sink.abort()
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(out)
    row = {"file": out.name, "seed": job["seed"], "preset": preset, "variation": job["variation"],
           "seconds": round(job["seconds"], 3), "real": job.get("real") or "",
           "real_db": job["real_db"] if job.get("real") else "", "video": str(video or "")}
    row.update({k: (float(f"{v:.4g}") if isinstance(v, float) else v) for k, v in asdict(params).items()})
    row["render_seconds"] = round(time.time() - started, 1)
    return row


def parse_presets(text: str) -> list[str]:
    names = list(PRESETS) if text.strip().lower() == "all" else [x.strip() for x in text.split(",") if x.strip()]
    unknown = [n for n in names if n not in PRESETS]
    if unknown or not names:
        raise argparse.ArgumentTypeError(f"preset không có: {', '.join(unknown) or text}; chọn trong {', '.join(PRESETS)} hoặc all")
    return names


def job_base(args, seed, seconds, output):
    return {"presets": args.preset, "variation": args.variation, "seed": seed, "seconds": seconds,
            "output": str(output), "loudness": args.loudness, "fade": args.fade,
            "real": args.real, "real_db": args.real_db, "library": args.library}


def cmd_presets(args):
    for name, (desc, _) in PRESETS.items():
        print(f"{name:10s} {desc}")
    return 0


def cmd_render(args):
    seed = rain.base_seed(args)
    out = Path(args.output)

    def progress(frac):
        print(f"\r  {frac * 100:5.1f}%", end="", file=sys.stderr, flush=True)

    job = job_base(args, seed, args.duration, out)
    job["progress"] = progress
    row = run_job(job)
    print(file=sys.stderr)
    print(f"Đã tạo {out}  preset={row['preset']} seed={seed}  ({row['render_seconds']}s)")
    extra = f" --real {args.real} --real-db {args.real_db}" if args.real else ""
    print(f"Tạo lại đúng bản này: --preset {row['preset']} --seed {seed} --variation {args.variation}{extra}")
    return 0


def cmd_batch(args):
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    seed0 = rain.base_seed(args)
    jobs = []
    for i in range(args.count):
        seed = seed0 + i
        preset = pick_params(args.preset, args.variation, seed)[0]
        out = outdir / f"{args.prefix}_{i + 1:04d}_{preset}_s{seed}.{args.format}"
        if out.exists() and not args.overwrite:
            print(f"Bỏ qua (đã có): {out.name}")
            continue
        jobs.append(job_base(args, seed, args.duration, out))
    return rain.run_jobs(jobs, args.jobs, outdir / "manifest.csv", run_job)


def cmd_video(args):
    videos = rain.find_videos(args.inputs)
    if not videos:
        raise SystemExit("Không có video nào để xử lý")
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    seed0 = rain.base_seed(args)
    jobs, bad = [], 0
    for i, video in enumerate(videos):
        out = outdir / f"{video.stem}{args.suffix}{'.webm' if video.suffix.lower() == '.webm' else '.mp4'}"
        if out.resolve() == video.resolve():
            raise SystemExit(f"File đầu ra trùng file gốc: {video}")
        if out.exists() and not args.overwrite:
            print(f"Bỏ qua (đã có): {out.name}")
            continue
        try:
            seconds = rain.media_duration(video)
        except RuntimeError as e:
            bad += 1
            print(f"LỖI {e}", file=sys.stderr)
            continue
        job = job_base(args, seed0 + i, seconds, out)
        job["video"] = str(video)
        jobs.append(job)
    return rain.run_jobs(jobs, args.jobs, outdir / "manifest.csv", run_job) or (1 if bad else 0)


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-p", "--preset", type=parse_presets, default=["campfire"],
                        help="kiểu lửa: " + ", ".join(PRESETS) + "; nhiều kiểu cách nhau dấu phẩy "
                             "(mỗi file chọn ngẫu nhiên một kiểu) hoặc all (mặc định: campfire)")
    common.add_argument("-v", "--variation", type=float, default=0.15,
                        help="mức khác nhau giữa các bản; 0 = giống hệt preset, 0.15 = mặc định, 0.3 = khác nhiều")
    common.add_argument("-s", "--seed", type=int, help="seed bắt đầu; cùng seed tạo lại đúng bản cũ (mặc định: ngẫu nhiên)")
    common.add_argument("--loudness", type=float, default=-20.0,
                        help="độ lớn trung bình, LUFS (mặc định: -20; lửa có nhiều tiếng nổ nên để thấp hơn mưa)")
    common.add_argument("--fade", type=float, default=3.0, help="fade vào/ra, giây (mặc định: 3)")
    common.add_argument("--real", metavar="THƯ_MỤC",
                        help="trộn thêm bản thu thật trong library/<THƯ_MỤC> (ví dụ: lua); bỏ trống = chỉ tổng hợp")
    common.add_argument("--real-db", type=float, default=-6.0,
                        help="độ lớn bản thu so với tiếng tổng hợp, dB (mặc định: -6 = một chút; 0 = ngang nhau)")
    common.add_argument("--library", default="library", help="thư mục thư viện âm thanh (mặc định: library)")

    parser = argparse.ArgumentParser(description="Tạo tiếng lửa bằng thuật toán, trộn thêm một chút bản thu thật.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("presets", help="liệt kê các kiểu lửa").set_defaults(func=cmd_presets)

    r = sub.add_parser("render", parents=[common], help="tạo một file tiếng lửa")
    r.add_argument("-d", "--duration", type=rain.parse_duration, default=600.0, help="độ dài, ví dụ 90s, 10m, 1h (mặc định: 10m)")
    r.add_argument("-o", "--output", required=True, help="file đầu ra: .flac .wav .mp3 .m4a .ogg .opus")
    r.set_defaults(func=cmd_render)

    b = sub.add_parser("batch", parents=[common], help="tạo nhiều file tiếng lửa khác nhau")
    b.add_argument("-n", "--count", type=int, required=True, help="số file cần tạo")
    b.add_argument("-d", "--duration", type=rain.parse_duration, required=True, help="độ dài mỗi file, ví dụ 10m, 1h")
    b.add_argument("--outdir", default="output", help="thư mục đầu ra (mặc định: output)")
    b.add_argument("--format", default="flac", choices=[e.lstrip(".") for e in rain.AUDIO_CODECS])
    b.add_argument("--prefix", default="fire", help="tiền tố tên file (mặc định: fire)")
    b.add_argument("-j", "--jobs", type=int, default=1, help="số file tạo song song (mặc định: 1)")
    b.add_argument("--overwrite", action="store_true", help="ghi đè file đã có")
    b.set_defaults(func=cmd_batch)

    v = sub.add_parser("video", parents=[common], help="ghép tiếng lửa riêng cho từng video")
    v.add_argument("inputs", nargs="+", help="file video hoặc thư mục chứa video")
    v.add_argument("--outdir", default="output", help="thư mục đầu ra (mặc định: output)")
    v.add_argument("--suffix", default="_fire", help="hậu tố tên file đầu ra (mặc định: _fire)")
    v.add_argument("-j", "--jobs", type=int, default=1, help="số video xử lý song song (mặc định: 1)")
    v.add_argument("--overwrite", action="store_true", help="ghi đè file đã có")
    v.set_defaults(func=cmd_video)
    return parser


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    if args.command != "presets":
        missing = [tool for tool in ("ffmpeg", "ffprobe") if not shutil.which(tool)]
        if missing:
            raise SystemExit(f"Cần cài {' và '.join(missing)} (https://ffmpeg.org/download.html)")
        if args.variation < 0:
            raise SystemExit("--variation phải >= 0")
        if args.real:  # measure the recordings once here so worker processes find them cached
            real_files(args.library, args.real)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
