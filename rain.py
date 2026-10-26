#!/usr/bin/env python3
"""Tạo tiếng mưa bằng thuật toán: mỗi seed cho ra một bản tiếng mưa khác nhau.

Ví dụ:
  python rain.py presets
  python rain.py render -p medium -d 10m -o mua.flac
  python rain.py batch -p light,medium,heavy -n 50 -d 1h --outdir output
  python rain.py video videos/ --outdir output
"""
from __future__ import annotations

import argparse
import csv
import itertools
import math
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

import numpy as np

SAMPLE_RATE = 48000
CHUNK_SECONDS = 2.0
CALIBRATION_SECONDS = 30.0
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".m4v", ".webm", ".avi"}
AUDIO_CODECS = {
    ".wav": ["-c:a", "pcm_s16le", "-rf64", "auto"],
    ".flac": ["-c:a", "flac"],
    ".mp3": ["-c:a", "libmp3lame", "-b:a", "320k"],
    ".m4a": ["-c:a", "aac", "-b:a", "256k"],
    ".aac": ["-c:a", "aac", "-b:a", "256k"],
    ".ogg": ["-c:a", "libvorbis", "-q:a", "6"],
    ".opus": ["-c:a", "libopus", "-b:a", "192k"],
}


@dataclass(frozen=True)
class RainParams:
    hiss_level: float  # độ lớn tiếng rào rào
    hiss_low_hz: float  # cắt tần số thấp của tiếng rào rào
    hiss_high_hz: float  # cắt tần số cao; thấp hơn = mưa nghe xa, êm hơn
    hiss_tilt: float  # độ nghiêng phổ; lớn hơn = ấm hơn
    texture: float  # 0 = rào rào mịn, 1 = lách tách li ti
    texture_rate: float  # số hạt li ti mỗi giây
    rumble_level: float  # tiếng ù trầm của mưa lớn
    rumble_high_hz: float
    width: float  # độ rộng stereo, 0..1
    drop_rate: float  # số giọt rơi rõ nét mỗi giây
    drop_level: float  # độ lớn giọt điển hình so với tiếng rào rào
    drop_low_hz: float
    drop_high_hz: float
    drop_decay_ms: float
    drop_bubble: float  # tỉ lệ giọt có tiếng "tõm" của bọt nước, 0..1
    swell_db: float  # mưa to nhỏ dần theo thời gian, biên độ dB
    swell_seconds: float  # nhịp to nhỏ, giây
    thunder_per_min: float  # số tiếng sấm trung bình mỗi phút
    thunder_level: float
    # Mái tôn: mọi giọt đập vào cùng một tấm kim loại mỏng (0 = không có mái)
    roof_level: float = 0.0  # độ lớn tiếng mái tôn
    roof_rate: float = 0.0  # số giọt nhỏ ("tách") mỗi giây trên mái
    roof_big_rate: float = 0.0  # số giọt to ("bộp") mỗi giây
    roof_big_level: float = 0.0  # độ lớn giọt to so với tiếng mái
    roof_low_hz: float = 150.0  # dải tần của tấm tôn
    roof_high_hz: float = 6000.0
    roof_decay_ms: float = 30.0  # độ ngân của tấm tôn ở 1 kHz
    roof_ring: float = 0.25  # 0 = tiếng tôn đục, 1 = ngân thành tiếng rõ


_HEAVY = RainParams(
    hiss_level=1.0, hiss_low_hz=400, hiss_high_hz=11000, hiss_tilt=0.2,
    texture=0.35, texture_rate=3500, rumble_level=0.5, rumble_high_hz=500,
    width=0.9, drop_rate=110, drop_level=0.9, drop_low_hz=1200, drop_high_hz=4000,
    drop_decay_ms=14, drop_bubble=0.25, swell_db=5, swell_seconds=25,
    thunder_per_min=0, thunder_level=0,
)

_ROOF = RainParams(
    hiss_level=0.25, hiss_low_hz=600, hiss_high_hz=8000, hiss_tilt=0.3,
    texture=0.4, texture_rate=1500, rumble_level=0.25, rumble_high_hz=250,
    width=0.8, drop_rate=4, drop_level=0.8, drop_low_hz=1200, drop_high_hz=3500,
    drop_decay_ms=14, drop_bubble=0.6, swell_db=4, swell_seconds=30,
    thunder_per_min=0, thunder_level=0,
    roof_level=1.0, roof_rate=2500, roof_big_rate=14, roof_big_level=2.5,
    roof_low_hz=150, roof_high_hz=6000, roof_decay_ms=30, roof_ring=0.12,
)

PRESETS: dict[str, tuple[str, RainParams]] = {
    "light": ("Mưa nhẹ, lất phất", RainParams(
        hiss_level=0.5, hiss_low_hz=900, hiss_high_hz=7000, hiss_tilt=0.3,
        texture=0.55, texture_rate=900, rumble_level=0.12, rumble_high_hz=250,
        width=0.75, drop_rate=18, drop_level=1.0, drop_low_hz=1800, drop_high_hz=5000,
        drop_decay_ms=10, drop_bubble=0.35, swell_db=3, swell_seconds=40,
        thunder_per_min=0, thunder_level=0,
    )),
    "medium": ("Mưa vừa, đều hạt", RainParams(
        hiss_level=0.8, hiss_low_hz=600, hiss_high_hz=9000, hiss_tilt=0.25,
        texture=0.45, texture_rate=1800, rumble_level=0.3, rumble_high_hz=350,
        width=0.85, drop_rate=45, drop_level=1.1, drop_low_hz=1500, drop_high_hz=4500,
        drop_decay_ms=12, drop_bubble=0.3, swell_db=4, swell_seconds=30,
        thunder_per_min=0, thunder_level=0,
    )),
    "heavy": ("Mưa lớn, nặng hạt", _HEAVY),
    "storm": ("Mưa giông có sấm", replace(
        _HEAVY, swell_db=6, swell_seconds=20, thunder_per_min=0.6, thunder_level=2.5,
    )),
    "roof": ("Mưa rào trên mái tôn", _ROOF),
    "roof_light": ("Mưa nhẹ trên mái tôn, lộp độp", replace(
        _ROOF, hiss_level=0.12, rumble_level=0.06, drop_rate=2, swell_db=3, swell_seconds=40,
        roof_rate=30, roof_big_rate=6, roof_big_level=2.5, roof_decay_ms=18, roof_ring=0.35,
    )),
}

# Parameters limited to 0..1 are varied additively, everything else multiplicatively.
BOUNDED = {"width", "texture", "drop_bubble", "roof_ring"}


def vary_params(base: RainParams, variation: float, rng: np.random.Generator) -> RainParams:
    """Jitter every numeric parameter by up to about ±variation (0.15 ≈ ±16%)."""
    if variation <= 0:
        return base
    changes = {}
    for f in fields(base):
        value = getattr(base, f.name)
        u = rng.uniform(-1.0, 1.0)
        if f.name in BOUNDED:
            changes[f.name] = float(np.clip(value + 0.5 * variation * u, 0.0, 1.0))
        else:
            changes[f.name] = float(value) * math.exp(variation * u)
    params = replace(base, **changes)
    for lo, hi in (("hiss_low_hz", "hiss_high_hz"), ("drop_low_hz", "drop_high_hz"), ("roof_low_hz", "roof_high_hz")):
        a, b = sorted((getattr(params, lo), getattr(params, hi)))
        params = replace(params, **{lo: a, hi: max(b, a * 1.2)})
    return params


def pick_params(presets: list[str], variation: float, seed: int) -> tuple[str, RainParams]:
    rng = np.random.default_rng([seed, 0])
    name = presets[int(rng.integers(len(presets)))]
    return name, vary_params(PRESETS[name][1], variation, rng)


def band(f, low, high, tilt=0.0, low_order=2, high_order=2):
    """Butterworth-shaped band-pass magnitude with a spectral tilt around 1 kHz."""
    highpass = 1.0 / np.sqrt(1.0 + (low / f) ** (2 * low_order))
    lowpass = 1.0 / np.sqrt(1.0 + (f / high) ** (2 * high_order))
    return highpass * lowpass * (f / 1000.0) ** (-tilt)


def widen(x: np.ndarray, width: float) -> np.ndarray:
    """Mix two independent channels: width 1 keeps them independent, 0 makes them mono."""
    theta = (1.0 - width) * math.pi / 4
    c, s = math.cos(theta), math.sin(theta)
    return np.stack([c * x[0] + s * x[1], s * x[0] + c * x[1]])


class ShapedNoise:
    """Endless noise with a given magnitude spectrum and unit variance.

    Independent frames are filtered in the frequency domain and overlap-added with a
    sqrt-Hann window at 50% overlap, which keeps the variance constant over time.
    With texture > 0, part of the excitation is sparse impulses, so the noise crackles.
    """

    def __init__(self, rng, sr, magnitude, channels=2, frame=8192, texture=0.0, texture_rate=0.0):
        self.rng, self.channels, self.frame, self.hop = rng, channels, frame, frame // 2
        mag = magnitude(np.maximum(np.fft.rfftfreq(frame, 1.0 / sr), 1.0))
        mag[0] = 0.0
        self.mag = (mag * math.sqrt(frame / (2.0 * np.sum(mag ** 2)))).astype(np.float32)
        self.active = np.flatnonzero(self.mag > self.mag.max() * 1e-3)
        n = np.arange(frame)
        self.window = np.sqrt(0.5 - 0.5 * np.cos(2 * np.pi * n / frame)).astype(np.float32)
        self.texture = float(np.clip(texture, 0.0, 1.0))
        self.impulses_per_frame = max(texture_rate, 1.0) * frame / sr
        self.carry = np.zeros((channels, self.hop), np.float32)
        self.buffer = np.zeros((channels, 0), np.float32)

    def _frames(self, m):
        shape = (self.channels, m)
        if self.texture > 0:
            excitation = self.rng.standard_normal(shape + (self.frame,), dtype=np.float32)
            excitation *= math.sqrt(1.0 - self.texture)
            counts = self.rng.poisson(self.impulses_per_frame, size=self.channels * m)
            total = int(counts.sum())
            if total:
                rows = np.repeat(np.arange(counts.size), counts)
                cols = self.rng.integers(0, self.frame, total)
                # Log-normal magnitudes with unit mean square: varied, but less spiky than Gaussian.
                scale = math.sqrt(self.texture * self.frame / self.impulses_per_frame)
                amps = np.exp(self.rng.normal(-0.35 ** 2, 0.35, total)) * self.rng.choice([-scale, scale], total)
                np.add.at(excitation.reshape(-1, self.frame), (rows, cols), amps.astype(np.float32))
            spectrum = np.fft.rfft(excitation, axis=-1)
        else:
            k = self.active.size
            spectrum = np.zeros(shape + (self.mag.size,), np.complex64)
            spectrum[..., self.active] = (
                self.rng.standard_normal(shape + (k,), dtype=np.float32)
                + 1j * self.rng.standard_normal(shape + (k,), dtype=np.float32)
            ) * np.float32(math.sqrt(self.frame / 2))
        return np.fft.irfft(spectrum * self.mag, n=self.frame, axis=-1).astype(np.float32) * self.window

    def _hops(self, m):
        frames = self._frames(m)
        first, second = frames[..., : self.hop], frames[..., self.hop :]
        previous = np.concatenate([self.carry[:, None, :], second[:, :-1, :]], axis=1)
        self.carry = second[:, -1, :]
        return (first + previous).reshape(self.channels, -1)

    def read(self, n):
        missing = n - self.buffer.shape[1]
        if missing > 0:
            self.buffer = np.concatenate([self.buffer, self._hops(-(-missing // self.hop))], axis=1)
        out, self.buffer = self.buffer[:, :n], self.buffer[:, n:]
        return out


class Swell:
    """Slowly wandering gain (a slow and a fast AR(1) process) so the rain rises and eases."""

    def __init__(self, rng, sr, depth_db, period_s, control_rate=50):
        self.rng, self.step, self.depth = rng, max(1, sr // control_rate), depth_db
        dt = 1.0 / control_rate
        self.coef = (math.exp(-dt / max(period_s, 0.5)), math.exp(-dt / max(period_s / 6, 0.5)))
        self.state = [0.0, 0.0]  # start at the nominal level
        self.last = self._value()
        self.buffer = np.zeros(0)

    def _value(self):
        return 0.75 * self.state[0] + 0.66 * self.state[1]

    def _block(self, m):
        values = np.empty(m + 1)
        values[0] = self.last
        (c1, c2), noise = self.coef, self.rng.standard_normal((m, 2)).tolist()
        k1, k2 = math.sqrt(1 - c1 * c1), math.sqrt(1 - c2 * c2)
        s1, s2 = self.state
        for i, (n1, n2) in enumerate(noise, 1):
            s1, s2 = c1 * s1 + k1 * n1, c2 * s2 + k2 * n2
            values[i] = 0.75 * s1 + 0.66 * s2
        self.state, self.last = [s1, s2], values[-1]
        return np.interp(np.arange(m * self.step) / self.step, np.arange(m + 1), values)

    def read(self, n):
        missing = n - self.buffer.size
        if missing > 0:
            self.buffer = np.concatenate([self.buffer, self._block(-(-missing // self.step))])
        out, self.buffer = self.buffer[:n], self.buffer[n:]
        return 10.0 ** (self.depth * np.clip(out, -2.5, 2.5) / 40.0)


def _loguniform(rng, lo, hi):
    return math.exp(rng.uniform(math.log(lo), math.log(hi)))


def _tick(rng, t, tau, smooth):
    """Short decaying click; the moving average keeps it clear of the very top octave."""
    tick = np.diff(rng.standard_normal(t.size + 1)) * np.exp(-t / tau)
    return np.convolve(tick, np.ones(smooth) / smooth, mode="same")


def _trim(x, floor=1e-3):
    """Normalise a mono (n,) or stereo (2, n) kernel to unit peak and drop its silent tail."""
    x = x / np.max(np.abs(x))
    keep = np.flatnonzero((np.abs(x).max(axis=0) if x.ndim == 2 else np.abs(x)) > floor)
    return x[..., : keep[-1] + 1].astype(np.float32)


def water_drop(rng, sr, p: RainParams):
    """Impact tick, plus a rising bubble 'plink' or a short surface tap."""
    tau = p.drop_decay_ms / 1000 * rng.uniform(0.6, 1.5)
    n = int(sr * (tau * 6 + 0.004))
    t = np.arange(n) / sr
    tick = _tick(rng, t, rng.uniform(0.0006, 0.002), int(rng.integers(2, 5)))
    drop = tick * rng.uniform(0.6, 1.0)
    f0 = _loguniform(rng, p.drop_low_hz, p.drop_high_hz)
    if rng.random() < p.drop_bubble:
        delay = rng.uniform(0.0, 0.004)
        tb = np.clip(t - delay, 0.0, None)
        freq = f0 * (1 + rng.uniform(0.05, 0.25) * tb / tau)
        tone = np.sin(2 * np.pi * np.cumsum(freq) / sr) * np.exp(-tb / tau) * (t >= delay)
        drop += tone * rng.uniform(0.5, 1.2)
    else:
        tone = np.sin(2 * np.pi * f0 * t) * np.exp(-t / (tau * 0.4))
        drop += tone * rng.uniform(0.2, 0.6)
    return _trim(drop)


class Drops:
    """Distinct events placed at random from a slowly refreshed bank of sounds.

    make(rng) returns a mono kernel, panned at random within width, or a stereo (2, n) kernel.
    """

    def __init__(self, rng, sr, rate, level, make, width=0.0, bank_size=48):
        self.rng, self.sr, self.rate, self.level, self.make, self.width = rng, sr, rate, level, make, width
        self.bank = [make(rng) for _ in range(bank_size)]
        self.carry = np.zeros((2, 0), np.float32)

    def read(self, n, gain):
        rng = self.rng
        peak = float(gain.max())
        count = int(rng.poisson(self.rate * peak * n / self.sr))
        pos = rng.integers(0, n, count)
        pos = pos[rng.random(count) < gain[pos] / peak]
        amps = self.level * np.minimum(np.exp(rng.normal(0.0, 0.5, pos.size)), math.e)
        angle = (rng.uniform(-1, 1, pos.size) * self.width + 1) * math.pi / 4
        left, right = amps * np.cos(angle), amps * np.sin(angle)
        which = rng.integers(0, len(self.bank), pos.size)
        longest = max(max(k.shape[-1] for k in self.bank), self.carry.shape[1])
        out = np.zeros((2, n + longest), np.float32)
        out[:, : self.carry.shape[1]] += self.carry
        for s, w, a, gl, gr in zip(pos.tolist(), which.tolist(), amps.tolist(), left.tolist(), right.tolist()):
            k = self.bank[w]
            if k.ndim == 2:
                out[:, s : s + k.shape[1]] += k * a
            else:
                out[0, s : s + k.size] += k * gl
                out[1, s : s + k.size] += k * gr
        self.carry = out[:, n:]
        for _ in range(max(1, len(self.bank) // 16)):
            self.bank[int(rng.integers(len(self.bank)))] = self.make(rng)
        return out[:, :n]


class Convolver:
    """Streaming overlap-add convolution of (groups, n) inputs with fixed (groups, channels, L)
    impulse responses; the results of all groups are summed into (channels, n)."""

    def __init__(self, irs, block):
        self.block, self.length = block, irs.shape[-1]
        self.nfft = 1 << (block + self.length - 2).bit_length()
        self.spectra = np.fft.rfft(irs, n=self.nfft, axis=-1).astype(np.complex64)
        self.tail = np.zeros((irs.shape[1], self.length - 1), np.float32)

    def process(self, x):
        out = []
        for start in range(0, x.shape[1], self.block):
            part = x[:, start : start + self.block]
            n = part.shape[1]
            spectrum = np.einsum("gf,gcf->cf", np.fft.rfft(part, n=self.nfft, axis=-1), self.spectra)
            y = np.fft.irfft(spectrum, n=self.nfft, axis=-1)[:, : n + self.length - 1].astype(np.float32)
            y[:, : self.length - 1] += self.tail
            self.tail = y[:, n:]
            out.append(y[:, :n])
        return np.concatenate(out, axis=1)


def raised_pulse(rng, sr, shortest, longest):
    """Force of a drop hitting a surface; longer pulses (bigger drops) sound duller."""
    m = max(1, int(round(sr * rng.uniform(shortest, longest))))
    w = np.hanning(m + 2)[1:-1]
    return w / w.sum()


def sheet_response(rng, sr, p: RainParams, tones):
    """Stereo impulse response of a thin metal sheet struck at one spot.

    A real sheet has thousands of closely spaced modes, modelled as noise that dies away
    faster at high frequencies, plus a few shared ringing modes (`tones`) that give the
    roof its own character. Each spot excites those modes with different strengths.
    """
    tau0 = p.roof_decay_ms / 1000

    def tau(f):
        return tau0 * np.clip(np.asarray(f) / 1000, 0.25, None) ** -0.6

    n = int(sr * 6 * float(tau(0)))
    t = np.arange(n) / sr
    f = np.fft.rfftfreq(n, 1.0 / sr)
    color = band(np.maximum(f, 1.0), p.roof_low_hz, p.roof_high_hz, 0.3)
    edges = np.geomspace(50, sr / 2, 15)
    dense = np.zeros((2, n))
    for c in range(2):
        spectrum = np.fft.rfft(rng.standard_normal(n)) * color
        for lo, hi in zip(edges[:-1], edges[1:]):
            mask = (f >= lo) & (f < hi)
            dense[c] += np.fft.irfft(spectrum * mask, n) * np.exp(-t / tau(math.sqrt(lo * hi)))
    dense /= np.sqrt(np.mean(dense ** 2))
    weights = rng.uniform(0, 1, tones.size) ** 2
    phases = rng.uniform(0, 2 * np.pi, (tones.size, 1))
    ring = (weights[:, None] * np.sin(2 * np.pi * tones[:, None] * t + phases)
            * np.exp(-t / (1.5 * tau(tones))[:, None])).sum(axis=0)
    ring /= np.sqrt(np.mean(ring ** 2)) + 1e-12
    return dense * math.sqrt(1 - p.roof_ring) + ring * math.sqrt(p.roof_ring)


class Roof:
    """Rain on a tin roof: every impact excites the same thin metal sheet.

    Small drops ("tách") are impulse trains convolved with the sheet's response at a few
    spots across the roof; big drops ("bộp") are added one by one from a bank of thuds.
    """

    SPOTS = 4

    def __init__(self, rng, sr, p: RainParams, block):
        self.rng, self.sr, self.p = rng, sr, p
        lo = 2.5 * p.roof_low_hz
        tones = np.exp(rng.uniform(math.log(lo), math.log(max(0.5 * p.roof_high_hz, 1.5 * lo)), 10))
        self.sheets = []
        for pan in np.linspace(-1, 1, self.SPOTS) * p.width * 0.8:
            angle = (pan + 1) * math.pi / 4
            gains = np.array([[math.cos(angle)], [math.sin(angle)]]) * math.sqrt(2)
            self.sheets.append(sheet_response(rng, sr, p, tones) * gains)
        responses = []
        for sheet in self.sheets:
            pulse = raised_pulse(rng, sr, 1e-4, 3e-4)
            responses.append(np.stack([np.convolve(sheet[c], pulse) for c in range(2)]))
        irs = np.zeros((self.SPOTS, 2, max(r.shape[1] for r in responses)))
        for i, r in enumerate(responses):
            irs[i, :, : r.shape[1]] = r
        irs /= np.sqrt(np.mean(np.sum(irs ** 2, axis=-1)))  # unit energy per channel on average
        self.small = Convolver(irs.astype(np.float32), block)
        self.scale = math.sqrt(sr / max(p.roof_rate, 1.0))  # unit RMS for the small drops
        self.big = Drops(rng, sr, p.roof_big_rate, p.roof_big_level, self._thud)

    def _thud(self, rng):
        sheet = self.sheets[int(rng.integers(self.SPOTS))]
        pulse = raised_pulse(rng, self.sr, 6e-4, 2e-3)
        return _trim(np.stack([np.convolve(sheet[c], pulse) for c in range(2)]))

    def read(self, n, gain):
        rng = self.rng
        peak = float(gain.max())
        count = int(rng.poisson(self.p.roof_rate * peak * n / self.sr))
        pos = rng.integers(0, n, count)
        pos = pos[rng.random(count) < gain[pos] / peak]
        amps = np.exp(rng.normal(-0.25, 0.5, pos.size)) * self.scale  # unit mean square
        x = np.zeros((self.SPOTS, n), np.float32)
        np.add.at(x, (rng.integers(0, self.SPOTS, pos.size), pos), amps.astype(np.float32))
        return self.small.process(x) + self.big.read(n, gain)


def _noise(rng, mag, n, channels=2):
    """One-shot noise of length n with the given rfft magnitude, unit RMS per channel."""
    spec = (rng.standard_normal((channels, mag.size)) + 1j * rng.standard_normal((channels, mag.size))) * mag
    x = np.fft.irfft(spec, n=n, axis=-1)
    return x / np.sqrt(np.mean(x ** 2, axis=-1, keepdims=True))


def make_thunder(rng, sr):
    """A rumble of several overlapping bursts, sometimes with a sharp crack for close strikes."""
    seconds = rng.uniform(5.0, 14.0)
    n = int(seconds * sr)
    t = np.arange(n) / sr
    f = np.maximum(np.fft.rfftfreq(n, 1.0 / sr), 1.0)
    close = rng.random() < 0.35
    cutoff = rng.uniform(150, 350) if close else rng.uniform(60, 160)
    y = widen(_noise(rng, band(f, 25, cutoff, 0, 2, 2), n), 0.6)
    env = np.zeros(n)
    for _ in range(int(rng.integers(2, 6))):
        tt = np.clip(t - rng.uniform(0, 0.4 * seconds), 0, None)
        env += rng.uniform(0.4, 1.0) * (1 - np.exp(-tt / rng.uniform(0.05, 0.6))) * np.exp(-tt / rng.uniform(0.8, 3.5))
    y *= env / env.max()
    if close:
        crack = _noise(rng, band(f, 600, 6000), n) * np.exp(-t / rng.uniform(0.08, 0.2))
        y += crack * rng.uniform(0.5, 0.9)
    y[:, -sr // 2 :] *= np.linspace(1, 0, sr // 2)
    angle = (rng.uniform(-0.6, 0.6) + 1) * math.pi / 4
    return (y * np.array([[math.cos(angle)], [math.sin(angle)]]) * math.sqrt(2)).astype(np.float32)


class RainSynth:
    def __init__(self, p: RainParams, seed: int, sr: int = SAMPLE_RATE):
        rngs = [np.random.default_rng([seed, i]) for i in range(1, 6)]
        self.p, self.sr = p, sr
        self.hiss = ShapedNoise(
            rngs[0], sr, lambda f: band(f, p.hiss_low_hz, p.hiss_high_hz, p.hiss_tilt),
            texture=p.texture, texture_rate=p.texture_rate,
        )
        self.rumble = ShapedNoise(rngs[1], sr, lambda f: band(f, 30.0, p.rumble_high_hz, 0.5, 2, 4))
        self.swell = Swell(rngs[2], sr, p.swell_db, p.swell_seconds)
        self.drops = Drops(rngs[3], sr, p.drop_rate, p.drop_level, lambda rng: water_drop(rng, sr, p), p.width)
        self.thunder_rng = rngs[4]
        self.thunders: list[list] = []  # [wave, index into wave at the start of the next chunk]
        self.roof = None
        if p.roof_level > 0:
            self.roof = Roof(np.random.default_rng([seed, 6]), sr, p, int(CHUNK_SECONDS * sr))
        self.bed_rms = math.sqrt(p.hiss_level ** 2 + p.rumble_level ** 2 + p.roof_level ** 2)

    def read(self, n):
        """Return (bed, thunder, swell gain) for the next n samples."""
        p = self.p
        gain = self.swell.read(n).astype(np.float32)
        bed = widen(self.hiss.read(n), p.width) * (p.hiss_level * gain)
        bed += widen(self.rumble.read(n), p.width * 0.5) * (p.rumble_level * np.sqrt(gain))
        bed += self.drops.read(n, gain)
        if self.roof:
            bed += self.roof.read(n, gain) * np.float32(self.p.roof_level)
        return bed, self._thunder(n), gain

    def _thunder(self, n):
        out = np.zeros((2, n), np.float32)
        p, rng = self.p, self.thunder_rng
        if p.thunder_per_min > 0:
            for start in np.sort(rng.integers(0, n, rng.poisson(p.thunder_per_min / 60 * n / self.sr))):
                wave = make_thunder(rng, self.sr) * np.float32(p.thunder_level * self.bed_rms)
                self.thunders.append([wave, -int(start)])
        alive = []
        for wave, pos in self.thunders:
            a, b = max(0, -pos), min(n, wave.shape[1] - pos)
            if b > a:
                out[:, a:b] += wave[:, a + pos : b + pos]
            if pos + n < wave.shape[1]:
                alive.append([wave, pos + n])
        self.thunders = alive
        return out


def soft_clip(x, threshold=0.7, ceiling=0.89):
    """Leave x untouched below threshold and bend it smoothly towards ceiling (-1 dBFS)."""
    over = np.abs(x) > threshold
    if over.any():
        span = ceiling - threshold
        x = x.copy()
        x[over] = np.sign(x[over]) * (threshold + span * np.tanh((np.abs(x[over]) - threshold) / span))
    return x


def k_weighting(f):
    """Complex BS.1770 K-weighting response at frequencies f (Hz); coefficients are given at 48 kHz."""
    z = np.exp(-2j * np.pi * np.minimum(f, 24000.0) / 48000.0)
    shelf = (1.53512485958697 - 2.69169618940638 * z + 1.19839281085285 * z * z) / (
        1 - 1.69065929318241 * z + 0.73248077421585 * z * z)
    highpass = (1 - 2 * z + z * z) / (1 - 1.99004745483398 * z + 0.99007225036621 * z * z)
    return shelf * highpass


def loudness_lufs(x: np.ndarray, sr: int) -> float:
    """Ungated BS.1770 loudness of a (channels, n) signal, K-weighting applied in the frequency domain."""
    f = np.fft.rfftfreq(x.shape[1], 1.0 / sr)
    power = np.abs(np.fft.rfft(x, axis=-1)) ** 2 * np.abs(k_weighting(f)) ** 2
    mean_square = 2.0 * power[:, 1:].sum(axis=-1) / x.shape[1] ** 2
    return -0.691 + 10 * math.log10(max(float(mean_square.sum()), 1e-20))


def rain_chunks(p: RainParams, seed: int, total: int, sr=SAMPLE_RATE, loudness=-18.0):
    """Yield float32 (2, n) chunks of rain, `total` samples in all, with the bed at `loudness` LUFS."""
    synth = RainSynth(p, seed, sr)
    chunk = int(CHUNK_SECONDS * sr)

    def chunks():
        done = 0
        while done < total:
            n = min(chunk, total - done)
            yield synth.read(n)
            done += n

    stream = chunks()
    # Calibrate on the first seconds of the bed with the swell divided out,
    # so every variant sits around the same loudness.
    warmup, count = [], 0
    for item in stream:
        warmup.append(item)
        count += item[0].shape[1]
        if count >= min(total, CALIBRATION_SECONDS * sr):
            break
    if not warmup:
        return
    nominal = np.concatenate([bed / gain for bed, _, gain in warmup], axis=1)
    gain_out = np.float32(10 ** ((loudness - loudness_lufs(nominal, sr)) / 20))
    del nominal
    for bed, thunder, _ in itertools.chain(warmup, stream):
        yield (bed + thunder) * gain_out


def finish(chunks, total, sink, sr=SAMPLE_RATE, fade=3.0, progress=None):
    """Apply fade in/out and the soft ceiling to a stream of chunks and hand them to sink."""
    fade_n = min(int(fade * sr), total // 2)
    pos = 0
    for y in chunks:
        n = y.shape[1]
        if fade_n and (pos < fade_n or pos + n > total - fade_n):
            idx = np.arange(pos, pos + n)
            y = y * (np.sin(np.minimum(1.0, np.minimum(idx, total - 1 - idx) / fade_n) * math.pi / 2) ** 2).astype(np.float32)
        sink(soft_clip(y))
        pos += n
        if progress:
            progress(pos / total)


def render(p: RainParams, seed: int, seconds: float, sink, sr=SAMPLE_RATE, loudness=-18.0, fade=3.0, progress=None):
    """Stream `seconds` of rain to sink(float32 array of shape (2, n)) in chunks."""
    total = int(round(seconds * sr))
    finish(rain_chunks(p, seed, total, sr, loudness), total, sink, sr, fade, progress)


class FFmpegSink:
    """Pipe float32 stereo audio into ffmpeg, either as an audio file or muxed into a video."""

    def __init__(self, output: Path, sr=SAMPLE_RATE, video: Path | None = None):
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
        if video:
            cmd += ["-i", str(video)]
        cmd += ["-f", "f32le", "-ar", str(sr), "-ac", "2", "-i", "pipe:0"]
        suffix = output.suffix.lower()
        if video:
            audio = ["-c:a", "libopus", "-b:a", "192k"] if suffix == ".webm" else ["-c:a", "aac", "-b:a", "256k"]
            cmd += ["-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", *audio, "-shortest"]
            if suffix in {".mp4", ".mov", ".m4v"}:
                cmd += ["-movflags", "+faststart"]
        else:
            if suffix not in AUDIO_CODECS:
                raise ValueError(f"Không hỗ trợ định dạng {suffix}; dùng một trong {', '.join(AUDIO_CODECS)}")
            cmd += AUDIO_CODECS[suffix]
        cmd.append(str(output))
        self.log = tempfile.TemporaryFile()
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=self.log)

    def write(self, y):
        try:
            self.proc.stdin.write(np.ascontiguousarray(y.T, dtype="<f4").tobytes())
        except BrokenPipeError:
            self.close()

    def close(self):
        if self.proc.stdin and not self.proc.stdin.closed:
            try:
                self.proc.stdin.close()
            except BrokenPipeError:
                pass
        if self.proc.wait() != 0:
            self.log.seek(0)
            message = self.log.read().decode(errors="replace").strip()
            self.log.close()
            raise RuntimeError("ffmpeg lỗi: " + message)
        self.log.close()

    def abort(self):
        self.proc.kill()
        self.proc.wait()
        self.log.close()


def run_job(job: dict) -> dict:
    """Render one output file. Top-level so it can run in a worker process."""
    started = time.time()
    preset, params = pick_params(job["presets"], job["variation"], job["seed"])
    out = Path(job["output"])
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".part" + out.suffix)
    video = Path(job["video"]) if job.get("video") else None
    sink = FFmpegSink(tmp, video=video)
    try:
        render(params, job["seed"], job["seconds"], sink.write, loudness=job["loudness"], fade=job["fade"],
               progress=job.get("progress"))
        sink.close()
    except BaseException:
        sink.abort()
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(out)
    row = {"file": out.name, "seed": job["seed"], "preset": preset, "variation": job["variation"],
           "seconds": round(job["seconds"], 3), "video": str(video or "")}
    row.update({k: (float(f"{v:.4g}") if isinstance(v, float) else v) for k, v in asdict(params).items()})
    row["render_seconds"] = round(time.time() - started, 1)
    return row


def append_manifest(path: Path, rows: list[dict]):
    if not rows:
        return
    new = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        if new:
            writer.writeheader()
        writer.writerows(rows)


def run_jobs(jobs: list[dict], workers: int, manifest: Path, func=None):
    """Run render jobs (sequentially or in worker processes), appending each result to manifest."""
    func = func or run_job
    total, done, failed = len(jobs), 0, 0

    def report(row):
        nonlocal done
        done += 1
        append_manifest(manifest, [row])
        kind = f"preset={row['preset']}" if "preset" in row else f"recipe={row.get('recipe', '')}"
        print(f"[{done}/{total}] {row['file']}  {kind} seed={row['seed']}  ({row['render_seconds']}s)")

    if workers <= 1:
        for job in jobs:
            try:
                report(func(job))
            except Exception as e:  # keep going with the remaining files
                failed += 1
                print(f"LỖI {job['output']}: {e}", file=sys.stderr)
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(func, job): job for job in jobs}
            for future in as_completed(futures):
                try:
                    report(future.result())
                except Exception as e:
                    failed += 1
                    print(f"LỖI {futures[future]['output']}: {e}", file=sys.stderr)
    print(f"Xong {done}/{total} file, ghi thông số vào {manifest}")
    return 1 if failed else 0


def parse_duration(text: str) -> float:
    """Accept 90, 90s, 10m, 1h30m, 1.5h, 01:30:00 or 2:30."""
    s = text.strip().lower()
    try:
        if ":" in s:
            seconds = 0.0
            for part in s.split(":"):
                seconds = seconds * 60 + float(part)
        else:
            m = re.fullmatch(r"(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m)?(?:(\d+(?:\.\d+)?)s?)?", s.replace(" ", ""))
            if not m or not any(m.groups()):
                raise ValueError
            h, mi, se = (float(g) if g else 0.0 for g in m.groups())
            seconds = h * 3600 + mi * 60 + se
    except ValueError:
        raise argparse.ArgumentTypeError(f"không hiểu độ dài '{text}' (ví dụ: 90s, 10m, 1h30m, 01:30:00)")
    if seconds <= 0:
        raise argparse.ArgumentTypeError("độ dài phải lớn hơn 0")
    return seconds


def parse_presets(text: str) -> list[str]:
    names = list(PRESETS) if text.strip().lower() == "all" else [x.strip() for x in text.split(",") if x.strip()]
    unknown = [n for n in names if n not in PRESETS]
    if unknown or not names:
        raise argparse.ArgumentTypeError(f"preset không có: {', '.join(unknown) or text}; chọn trong {', '.join(PRESETS)} hoặc all")
    return names


def media_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(out.stdout.strip())
    except ValueError:
        raise RuntimeError(f"không đọc được độ dài video {path}: {out.stderr.strip()}")


def find_videos(inputs: list[str]) -> list[Path]:
    videos = []
    for item in inputs:
        path = Path(item)
        if path.is_dir():
            videos += sorted(p for p in path.iterdir() if p.suffix.lower() in VIDEO_EXTS and ".part." not in p.name)
        elif path.is_file():
            videos.append(path)
        else:
            raise SystemExit(f"Không tìm thấy: {item}")
    return videos


def base_seed(args) -> int:
    return args.seed if args.seed is not None else secrets.randbelow(2**31)


def cmd_presets(args):
    for name, (desc, _) in PRESETS.items():
        print(f"{name:8s} {desc}")
    return 0


def cmd_render(args):
    seed = base_seed(args)
    out = Path(args.output)

    def progress(frac):
        print(f"\r  {frac * 100:5.1f}%", end="", file=sys.stderr, flush=True)

    row = run_job({"presets": args.preset, "variation": args.variation, "seed": seed, "seconds": args.duration,
                   "output": str(out), "loudness": args.loudness, "fade": args.fade, "progress": progress})
    print(file=sys.stderr)
    print(f"Đã tạo {out}  preset={row['preset']} seed={seed}  ({row['render_seconds']}s)")
    print(f"Tạo lại đúng bản này: --preset {row['preset']} --seed {seed} --variation {args.variation}")
    return 0


def cmd_batch(args):
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    seed0 = base_seed(args)
    ext = args.format.lower().lstrip(".")
    jobs = []
    for i in range(args.count):
        seed = seed0 + i
        preset = pick_params(args.preset, args.variation, seed)[0]
        out = outdir / f"{args.prefix}_{i + 1:04d}_{preset}_s{seed}.{ext}"
        if out.exists() and not args.overwrite:
            print(f"Bỏ qua (đã có): {out.name}")
            continue
        jobs.append({"presets": args.preset, "variation": args.variation, "seed": seed, "seconds": args.duration,
                     "output": str(out), "loudness": args.loudness, "fade": args.fade})
    return run_jobs(jobs, args.jobs, outdir / "manifest.csv")


def cmd_video(args):
    videos = find_videos(args.inputs)
    if not videos:
        raise SystemExit("Không có video nào để xử lý")
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    seed0 = base_seed(args)
    jobs, seen, bad = [], set(), 0
    for i, video in enumerate(videos):
        ext = ".webm" if video.suffix.lower() == ".webm" else ".mp4"
        out = outdir / f"{video.stem}{args.suffix}{ext}"
        if out in seen:
            raise SystemExit(f"Hai video trùng tên đầu ra: {out.name}")
        seen.add(out)
        if out.resolve() == video.resolve():
            raise SystemExit(f"File đầu ra trùng file gốc: {video}")
        if out.exists() and not args.overwrite:
            print(f"Bỏ qua (đã có): {out.name}")
            continue
        try:
            seconds = media_duration(video)
        except RuntimeError as e:
            bad += 1
            print(f"LỖI {e}", file=sys.stderr)
            continue
        jobs.append({"presets": args.preset, "variation": args.variation, "seed": seed0 + i,
                     "seconds": seconds, "output": str(out), "video": str(video),
                     "loudness": args.loudness, "fade": args.fade})
    return run_jobs(jobs, args.jobs, outdir / "manifest.csv") or (1 if bad else 0)


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-p", "--preset", type=parse_presets, default=["medium"],
                        help="kiểu mưa: " + ", ".join(PRESETS) + "; nhiều kiểu cách nhau dấu phẩy "
                             "(mỗi file chọn ngẫu nhiên một kiểu) hoặc all (mặc định: medium)")
    common.add_argument("-v", "--variation", type=float, default=0.15,
                        help="mức khác nhau giữa các bản so với preset; 0 = giống hệt preset, "
                             "0.15 ≈ ±16%% (mặc định), 0.3 = khác nhiều")
    common.add_argument("-s", "--seed", type=int, help="seed bắt đầu; cùng seed sẽ tạo lại đúng bản cũ (mặc định: ngẫu nhiên)")
    common.add_argument("--loudness", type=float, default=-18.0,
                        help="độ lớn trung bình, LUFS (YouTube chuẩn hoá về -14; mặc định: -18)")
    common.add_argument("--fade", type=float, default=3.0, help="fade vào/ra, giây (mặc định: 3)")

    parser = argparse.ArgumentParser(description="Tạo tiếng mưa bằng thuật toán, mỗi seed một bản khác nhau.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("presets", help="liệt kê các kiểu mưa").set_defaults(func=cmd_presets)

    r = sub.add_parser("render", parents=[common], help="tạo một file tiếng mưa")
    r.add_argument("-d", "--duration", type=parse_duration, default=600.0, help="độ dài, ví dụ 90s, 10m, 1h30m (mặc định: 10m)")
    r.add_argument("-o", "--output", required=True, help="file đầu ra: .flac .wav .mp3 .m4a .ogg .opus")
    r.set_defaults(func=cmd_render)

    b = sub.add_parser("batch", parents=[common], help="tạo nhiều file tiếng mưa khác nhau")
    b.add_argument("-n", "--count", type=int, required=True, help="số file cần tạo")
    b.add_argument("-d", "--duration", type=parse_duration, required=True, help="độ dài mỗi file, ví dụ 10m, 1h")
    b.add_argument("--outdir", default="output", help="thư mục đầu ra (mặc định: output)")
    b.add_argument("--format", default="flac", choices=[e.lstrip(".") for e in AUDIO_CODECS], help="định dạng (mặc định: flac)")
    b.add_argument("--prefix", default="rain", help="tiền tố tên file (mặc định: rain)")
    b.add_argument("-j", "--jobs", type=int, default=1, help="số file tạo song song (mặc định: 1)")
    b.add_argument("--overwrite", action="store_true", help="ghi đè file đã có thay vì bỏ qua")
    b.set_defaults(func=cmd_batch)

    v = sub.add_parser("video", parents=[common], help="ghép tiếng mưa riêng cho từng video")
    v.add_argument("inputs", nargs="+", help="file video hoặc thư mục chứa video")
    v.add_argument("--outdir", default="output", help="thư mục đầu ra (mặc định: output)")
    v.add_argument("--suffix", default="_rain", help="hậu tố tên file đầu ra (mặc định: _rain)")
    v.add_argument("-j", "--jobs", type=int, default=1, help="số video xử lý song song (mặc định: 1)")
    v.add_argument("--overwrite", action="store_true", help="ghi đè file đã có thay vì bỏ qua")
    v.set_defaults(func=cmd_video)
    return parser


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):  # Vietnamese text on consoles without UTF-8
            stream.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    if args.command != "presets":
        missing = [tool for tool in ("ffmpeg", "ffprobe") if not shutil.which(tool)]
        if missing:
            raise SystemExit(f"Cần cài {' và '.join(missing)} (https://ffmpeg.org/download.html)")
        if args.variation < 0:
            raise SystemExit("--variation phải >= 0")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
