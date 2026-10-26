#!/usr/bin/env python3
"""Rain Mixer: trộn nhiều lớp tiếng mưa (bản thu thật hoặc tiếng tổng hợp) thành một bản hoàn chỉnh.

Mỗi lần xuất với một seed mới, các đoạn bản thu được chọn và nối lại khác nhau, âm lượng,
EQ, tốc độ lệch nhẹ, các tiếng sấm/giọt nước rơi vào lúc khác, nên mỗi bản là duy nhất.

Ví dụ:
  python rainmix.py studio
  python rainmix.py render mai_ton_dem -d 10m -o mai_ton.flac
  python rainmix.py batch mai_ton_dem -n 20 -d 1h --outdir output -j 4
  python rainmix.py video mai_ton_dem videos/ --outdir output
"""
from __future__ import annotations

import argparse
import io
import itertools
import json
import math
import re
import shutil
import subprocess
import sys
import threading
import time
import wave
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path

import numpy as np

import rain

SR = rain.SAMPLE_RATE
LAYER_REFERENCE = -23.0  # LUFS of every layer at gain 0 dB
EVENT_REFERENCE = -20.0  # momentary peak loudness of event sounds at gain 0 dB
AUDIO_EXTS = {".wav", ".flac", ".mp3", ".ogg", ".opus", ".m4a", ".aac", ".aif", ".aiff"}
CACHE_FILE = ".rainmix-cache.json"
DECODE_CACHE_SECONDS = 120.0  # files up to this length are decoded once per render
SYNTH_EVENTS = {
    "thunder": "Tiếng sấm (tổng hợp)",
    "drip": "Giọt nước rơi (tổng hợp)",
}


# ---------------------------------------------------------------- recipes

@dataclass
class Layer:
    name: str = "Lớp mới"
    type: str = "bed"  # "bed" = tiếng nền liên tục, "events" = âm rời rạc (sấm, giọt to...)
    source: str = ""  # thư mục trong thư viện, "synth:<preset>", "synth:thunder" hoặc "synth:drip"
    enabled: bool = True
    gain_db: float = 0.0
    highpass_hz: float = 0.0  # cắt bớt tiếng trầm dưới tần số này (0 = tắt)
    lowpass_hz: float = 20000.0  # cắt bớt tiếng chói trên tần số này
    width: float = 1.0  # 0 = mono, 1 = giữ nguyên, 2 = rộng gấp đôi
    speed: float = 1.0  # tốc độ phát bản thu: <1 trầm và chậm hơn, >1 cao và nhanh hơn
    swell_db: float = 2.0  # (nền) to nhỏ dần theo thời gian
    swell_seconds: float = 30.0
    per_minute: float = 4.0  # (sự kiện) số lần trung bình mỗi phút
    gain_spread_db: float = 6.0  # (sự kiện) chênh lệch âm lượng ngẫu nhiên giữa các lần
    pan_spread: float = 0.7  # (sự kiện) trải trái/phải, 0..1
    min_gap_seconds: float = 1.0  # (sự kiện) khoảng cách tối thiểu giữa hai lần

    @property
    def is_events(self) -> bool:
        kind = synth_kind(self.source)
        if kind:
            return kind in SYNTH_EVENTS
        return self.type == "events"


@dataclass
class Recipe:
    name: str = "Công thức mới"
    loudness: float = -18.0  # độ lớn các lớp nền, LUFS (âm rời rạc như sấm cộng thêm lên trên)
    variation: float = 0.15  # mức khác nhau giữa các bản
    fade: float = 3.0  # fade vào/ra, giây
    layers: list[Layer] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> Recipe:
        names = {f.name for f in fields(Layer)}
        layers = [Layer(**{k: v for k, v in item.items() if k in names}) for item in data.get("layers", [])]
        top = {f.name for f in fields(cls)} - {"layers"}
        return cls(layers=layers, **{k: v for k, v in data.items() if k in top})

    def to_dict(self) -> dict:
        return asdict(self)


def synth_kind(source: str) -> str | None:
    return source[len("synth:"):] if source.startswith("synth:") else None


def vary_layer(layer: Layer, variation: float, rng: np.random.Generator) -> Layer:
    """Nudge a layer's settings for one render; always draws the same number of numbers."""
    u = rng.uniform(-1.0, 1.0, 8)
    if variation <= 0:
        return layer
    return replace(
        layer,
        gain_db=layer.gain_db + 10 * variation * u[0],
        highpass_hz=layer.highpass_hz * math.exp(variation * u[1]),
        lowpass_hz=min(20000.0, layer.lowpass_hz * math.exp(variation * u[2])),
        speed=layer.speed * math.exp(0.2 * variation * u[3]),
        width=float(np.clip(layer.width + 0.5 * variation * u[4], 0.0, 2.0)),
        swell_db=layer.swell_db * math.exp(variation * u[5]),
        swell_seconds=layer.swell_seconds * math.exp(variation * u[6]),
        per_minute=layer.per_minute * math.exp(variation * u[7]),
    )


def load_recipe(spec: str, recipes_dir: Path) -> tuple[Recipe, Path]:
    path = Path(spec)
    if not path.suffix:
        path = recipes_dir / f"{spec}.json"
    if not path.is_file():
        raise SystemExit(f"Không tìm thấy công thức: {spec}")
    return Recipe.from_dict(json.loads(path.read_text(encoding="utf-8"))), path


def slugify(text: str) -> str:
    table = str.maketrans("àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ",
                          "aaaaaaaaaaaaaaaaaeeeeeeeeeeeiiiiiooooooooooooooooouuuuuuuuuuuyyyyyd")
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower().translate(table)).strip("_")
    return slug or "cong_thuc"


# ---------------------------------------------------------------- audio files

def decode(path: Path, start=0.0, duration=None, speed=1.0, highpass=0.0, lowpass=20000.0, sr=SR) -> np.ndarray:
    """Decode part of any audio file to float32 stereo (2, n) at sr, with speed change and filters."""
    filters = [f"aresample={sr}"]
    if abs(speed - 1.0) > 1e-4:
        filters += [f"asetrate={sr * speed:.3f}", f"aresample={sr}"]
    if highpass > 20:
        filters.append(f"highpass=f={highpass:.1f}")
    if lowpass < sr * 0.45:
        filters.append(f"lowpass=f={lowpass:.1f}")
    cmd = ["ffmpeg", "-v", "error", "-nostdin"]
    if start > 0:
        cmd += ["-ss", f"{start:.3f}"]
    if duration:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-i", str(path), "-af", ",".join(filters), "-f", "f32le", "-ac", "2", "-ar", str(sr), "-"]
    out = subprocess.run(cmd, capture_output=True)
    if out.returncode:
        raise RuntimeError(f"không đọc được {path.name}: {out.stderr.decode(errors='replace').strip()}")
    return np.frombuffer(out.stdout, "<f4").reshape(-1, 2).T.copy()


def momentary_max_lufs(x: np.ndarray, sr=SR) -> float:
    """Loudest 400 ms of a (2, n) signal, in LUFS (useful for one-shot sounds)."""
    f = np.fft.rfftfreq(x.shape[1], 1.0 / sr)
    k = np.fft.irfft(np.fft.rfft(x, axis=-1) * rain.k_weighting(f), n=x.shape[1], axis=-1)
    power = np.sum(k ** 2, axis=0)
    win = int(0.4 * sr)
    if power.size <= win:
        return -0.691 + 10 * math.log10(max(float(power.mean()), 1e-20))
    sums = np.cumsum(np.concatenate([[0.0], power]))
    windows = (sums[win:] - sums[:-win])[:: int(0.1 * sr)] / win
    return -0.691 + 10 * math.log10(max(float(windows.max()), 1e-20))


class Library:
    """Sound folders under a root directory. Durations and loudness are cached per file."""

    def __init__(self, root):
        self.root = Path(root)
        self.cache_path = self.root / CACHE_FILE
        try:
            self.cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.cache = {}
        self.lock = threading.Lock()
        self.dirty = False

    def resolve(self, rel: str) -> Path:
        path = (self.root / rel).resolve()
        if self.root.resolve() not in (path, *path.parents):
            raise ValueError(f"đường dẫn nằm ngoài thư viện: {rel}")
        return path

    def folders(self) -> dict[str, list[str]]:
        """Folder (relative path) -> audio files in it (relative paths), for every folder with sounds."""
        result: dict[str, list[str]] = {}
        if not self.root.is_dir():
            return result
        for path in sorted(self.root.rglob("*")):
            if path.is_file() and path.suffix.lower() in AUDIO_EXTS and not path.name.startswith("."):
                rel = path.relative_to(self.root)
                result.setdefault(rel.parent.as_posix(), []).append(rel.as_posix())
        return result

    def files(self, source: str) -> list[str]:
        if not source:
            return []
        try:
            path = self.resolve(source)
        except ValueError:
            return []
        if path.is_file():
            return [source] if path.suffix.lower() in AUDIO_EXTS else []
        return self.folders().get(Path(source).as_posix(), [])

    def info(self, rel: str, loudness=True) -> dict:
        path = self.resolve(rel)
        stat = path.stat()
        stamp = [stat.st_size, int(stat.st_mtime)]
        with self.lock:
            entry = dict(self.cache.get(rel) or {})
        if entry.get("stamp") != stamp:
            entry = {"stamp": stamp, "duration": rain.media_duration(path)}
        if loudness and "loudness" not in entry:
            # Measure up to two minutes from the middle of the file.
            length = min(entry["duration"], DECODE_CACHE_SECONDS)
            sample = decode(path, max(0.0, (entry["duration"] - length) / 2), length)
            entry["loudness"] = round(rain.loudness_lufs(sample.astype(np.float64), SR), 2) if sample.size else -99.0
            entry["peak_loudness"] = round(momentary_max_lufs(sample.astype(np.float64)), 2) if sample.size else -99.0
        with self.lock:
            if self.cache.get(rel) != entry:
                self.cache[rel] = entry
                self.dirty = True
        return entry

    def usable(self, files: list[str]) -> tuple[list[str], list[str]]:
        """Split files into ones that can be read and measured, and broken ones."""
        good, bad = [], []
        for rel in files:
            try:
                (good if self.info(rel)["duration"] >= 0.05 else bad).append(rel)
            except (OSError, RuntimeError, ValueError, KeyError):
                bad.append(rel)
        return good, bad

    def save(self):
        with self.lock:
            if not self.dirty or not self.root.is_dir():
                return
            tmp = self.cache_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.cache, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.cache_path)
            self.dirty = False

    def prepare(self, recipe: Recipe) -> list[str]:
        """Measure every file the recipe uses (so worker processes find it cached); return warnings."""
        warnings = []
        for layer in recipe.layers:
            if not layer.enabled or synth_kind(layer.source):
                continue
            files = self.files(layer.source)
            if not files:
                warnings.append(f"Lớp '{layer.name}': không có file âm thanh trong '{layer.source}'")
            _, bad = self.usable(files)
            if bad:
                warnings.append(f"Lớp '{layer.name}': bỏ qua file không đọc được: {', '.join(bad)}")
        self.save()
        return warnings


def _gain_for(loudness: float, reference: float) -> float:
    return 1.0 if loudness < -70 else 10 ** ((reference - loudness) / 20)


# ---------------------------------------------------------------- layer streams

class Buffered:
    """Base for streams that produce audio in pieces of their own size."""

    def __init__(self):
        self.buffer = np.zeros((2, 0), np.float32)

    def _more(self) -> np.ndarray:
        raise NotImplementedError

    def read(self, n):
        while self.buffer.shape[1] < n:
            self.buffer = np.concatenate([self.buffer, self._more()], axis=1)
        out, self.buffer = self.buffer[:, :n], self.buffer[:, n:]
        return out


class BedFromFiles(Buffered):
    """Endless bed made of random stretches of the source files, joined with equal-power crossfades."""

    def __init__(self, rng, library: Library, files: list[str], layer: Layer, sr=SR, crossfade=3.0):
        super().__init__()
        self.rng, self.library, self.layer, self.sr = rng, library, layer, sr
        self.files = [f for f in files if library.info(f)["duration"] >= 0.5]  # callers pass readable files
        if not self.files:
            raise RuntimeError(f"lớp '{layer.name}' không có file đủ dài")
        durations = np.array([library.info(f)["duration"] for f in self.files])
        self.weights = durations / durations.sum()
        self.crossfade = int(crossfade * sr)
        self.tail = None
        self.decoded: dict[str, np.ndarray] = {}

    def _segment(self):
        rel = self.files[int(self.rng.choice(len(self.files), p=self.weights))]
        info = self.library.info(rel)
        duration, layer = info["duration"], self.layer
        want = self.rng.uniform(20, 75) * layer.speed + 2 * self.crossfade / self.sr
        if duration <= want:  # short file: a random part of it, so repeats do not line up
            length = duration * self.rng.uniform(0.5, 1.0)
            start = self.rng.uniform(0, duration - length)
        else:
            length, start = want, self.rng.uniform(0, duration - want)
        gain = np.float32(_gain_for(info["loudness"], LAYER_REFERENCE))
        if duration <= DECODE_CACHE_SECONDS:
            if rel not in self.decoded:
                self.decoded[rel] = decode(self.library.resolve(rel), 0, None, layer.speed,
                                           layer.highpass_hz, layer.lowpass_hz, self.sr)
            whole = self.decoded[rel]
            a = int(start / layer.speed * self.sr)
            return whole[:, a : a + int(length / layer.speed * self.sr)] * gain
        seg = decode(self.library.resolve(rel), start, length, layer.speed, layer.highpass_hz, layer.lowpass_hz, self.sr)
        return seg * gain

    def _more(self):
        for _ in range(20):
            seg = self._segment()
            if seg.shape[1] >= 64:
                break
        else:
            raise RuntimeError(f"lớp '{self.layer.name}': không đọc được âm thanh")
        size = seg.shape[1]
        hold = min(self.crossfade, size // 3)  # kept back to crossfade into the next segment
        if self.tail is None:
            ready = seg[:, : size - hold]
        else:
            xf = min(self.crossfade, size // 3, self.tail.shape[1])
            theta = ((np.arange(xf) + 0.5) / xf * (math.pi / 2)).astype(np.float32)
            mixed = self.tail[:, self.tail.shape[1] - xf :] * np.cos(theta) + seg[:, :xf] * np.sin(theta)
            ready = np.concatenate([self.tail[:, : self.tail.shape[1] - xf], mixed, seg[:, xf : size - hold]], axis=1)
        self.tail = seg[:, size - hold :]
        return ready


class FirEq:
    """Linear-phase high/low-pass for streams that are not decoded through ffmpeg."""

    def __init__(self, highpass, lowpass, sr=SR, taps=2047):
        n = 8192
        f = np.maximum(np.fft.rfftfreq(n, 1.0 / sr), 1.0)
        mag = np.ones_like(f)
        if highpass > 20:
            mag /= np.sqrt(1 + (highpass / f) ** 4)
        if lowpass < sr * 0.45:
            mag /= np.sqrt(1 + (f / lowpass) ** 4)
        h = np.roll(np.fft.irfft(mag, n), taps // 2)[:taps] * np.hanning(taps)
        irs = np.zeros((2, 2, taps), np.float32)
        irs[0, 0] = irs[1, 1] = h
        self.conv = rain.Convolver(irs, 8192)

    def __call__(self, x):
        return self.conv.process(x)


class SynthBed(Buffered):
    """A rain.py preset as a layer, at the layer reference loudness."""

    def __init__(self, preset: str, seed: int, variation: float, layer: Layer, total: int, sr=SR):
        super().__init__()
        if preset not in rain.PRESETS:
            raise RuntimeError(f"không có kiểu mưa tổng hợp '{preset}'")
        _, params = rain.pick_params([preset], variation, seed)
        # Ask for a little more than needed: the EQ below delays the stream slightly.
        self.chunks = rain.rain_chunks(params, seed, total + 4096, sr, LAYER_REFERENCE)
        needs_eq = layer.highpass_hz > 20 or layer.lowpass_hz < sr * 0.45
        self.eq = FirEq(layer.highpass_hz, layer.lowpass_hz, sr) if needs_eq else None

    def _more(self):
        chunk = next(self.chunks, None)
        if chunk is None:
            return np.zeros((2, 4096), np.float32)
        return self.eq(chunk) if self.eq else chunk


class Events:
    """One-shot sounds at random times (a renewal process with a minimum gap)."""

    def __init__(self, rng, layer: Layer, make, sr=SR):
        self.rng, self.layer, self.make, self.sr = rng, layer, make, sr
        self.mean_gap = 60.0 / layer.per_minute if layer.per_minute > 0 else math.inf
        self.next_at = self._gap()
        self.pos = 0
        self.active: list[list] = []  # [wave, index into wave at the start of the next read]

    def _gap(self):
        if math.isinf(self.mean_gap):
            return math.inf
        return int(max(self.layer.min_gap_seconds, self.rng.exponential(self.mean_gap)) * self.sr)

    def read(self, n):
        out = np.zeros((2, n), np.float32)
        while self.next_at < self.pos + n:
            wave = self.make(self.rng)
            gain = 10 ** (self.rng.uniform(-0.5, 0.5) * self.layer.gain_spread_db / 20)
            angle = (self.rng.uniform(-1, 1) * self.layer.pan_spread + 1) * math.pi / 4
            pan = np.array([[math.cos(angle)], [math.sin(angle)]], np.float32) * np.float32(math.sqrt(2) * gain)
            self.active.append([wave * pan, self.pos - self.next_at])
            self.next_at += self._gap()
        alive = []
        for wave, at in self.active:
            a, b = max(0, -at), min(n, wave.shape[1] - at)
            if b > a:
                out[:, a:b] += wave[:, a + at : b + at]
            if at + n < wave.shape[1]:
                alive.append([wave, at + n])
        self.active = alive
        self.pos += n
        return out


def file_event_maker(library: Library, files: list[str], layer: Layer, sr=SR):
    decoded: dict[str, np.ndarray] = {}

    def make(rng):
        rel = files[int(rng.integers(len(files)))]
        if rel not in decoded:
            info = library.info(rel)
            wave_ = decode(library.resolve(rel), 0, min(info["duration"], DECODE_CACHE_SECONDS), layer.speed,
                           layer.highpass_hz, layer.lowpass_hz, sr)
            decoded[rel] = wave_ * np.float32(_gain_for(info["peak_loudness"], EVENT_REFERENCE))
        return decoded[rel]

    return make


def synth_event_maker(kind: str, layer: Layer, sr=SR):
    params = replace(rain.PRESETS["medium"][1], drop_bubble=0.7)
    eq = (layer.highpass_hz, layer.lowpass_hz)
    bank: list[np.ndarray] = []

    def create(rng):
        if kind == "thunder":
            x = rain.make_thunder(rng, sr)
        else:
            drop = rain.water_drop(rng, sr, params)
            x = np.stack([drop, drop])
        x = x.astype(np.float64)
        if eq[0] > 20 or eq[1] < sr * 0.45:
            f = np.maximum(np.fft.rfftfreq(x.shape[1], 1.0 / sr), 1.0)
            mag = 1 / np.sqrt(1 + (max(eq[0], 1.0) / f) ** 4) / np.sqrt(1 + (f / eq[1]) ** 4)
            x = np.fft.irfft(np.fft.rfft(x, axis=-1) * mag, n=x.shape[1], axis=-1)
        return (x * _gain_for(momentary_max_lufs(x), EVENT_REFERENCE)).astype(np.float32)

    def make(rng):
        if kind == "thunder":  # rare and long: every strike is new
            return create(rng)
        if not bank:
            bank.extend(create(rng) for _ in range(32))
        return bank[int(rng.integers(len(bank)))]

    return make


def set_width(x, width):
    if abs(width - 1.0) < 1e-3:
        return x
    mid, side = (x[0] + x[1]) * 0.5, (x[0] - x[1]) * (0.5 * width)
    return np.stack([mid + side, mid - side])


# ---------------------------------------------------------------- mixer

class Mixer:
    def __init__(self, recipe: Recipe, library: Library, seed: int, total: int, sr=SR):
        self.recipe, self.seed, self.sr = recipe, seed, sr
        self.parts = []  # (layer as rendered, stream, swell, linear gain)
        self.warnings = []
        for i, layer in enumerate(recipe.layers):
            rng = np.random.default_rng([seed, 100 + i])
            v = vary_layer(layer, recipe.variation, rng)
            if not layer.enabled or not layer.source:
                continue
            try:
                stream = self._stream(v, rng, library, seed + 7919 * (i + 1), total)
            except RuntimeError as e:
                self.warnings.append(str(e))
                continue
            if stream is None:
                self.warnings.append(f"Lớp '{layer.name}': không có file âm thanh trong '{layer.source}'")
                continue
            swell = rain.Swell(rng, sr, v.swell_db, v.swell_seconds) if not v.is_events and v.swell_db > 0 else None
            self.parts.append((v, stream, swell, np.float32(10 ** (v.gain_db / 20))))

    def _stream(self, v: Layer, rng, library, seed, total):
        kind = synth_kind(v.source)
        if kind in SYNTH_EVENTS:
            return Events(rng, v, synth_event_maker(kind, v, self.sr), self.sr)
        if kind is not None:
            return SynthBed(kind, seed, self.recipe.variation, v, total, self.sr)
        files, bad = library.usable(library.files(v.source))
        if bad:
            self.warnings.append(f"Lớp '{v.name}': bỏ qua file không đọc được: {', '.join(bad)}")
        if not files:
            return None
        if v.is_events:
            return Events(rng, v, file_event_maker(library, files, v, self.sr), self.sr)
        return BedFromFiles(rng, library, files, v, self.sr)

    def read(self, n):
        """Return (beds, events) for the next n samples."""
        beds = np.zeros((2, n), np.float32)
        events = np.zeros((2, n), np.float32)
        for v, stream, swell, gain in self.parts:
            x = set_width(stream.read(n), v.width) * gain
            if swell is not None:
                x = x * swell.read(n).astype(np.float32)
            if v.is_events:
                events += x
            else:
                beds += x
        return beds, events

    def summary(self) -> str:
        return "; ".join(f"{v.name}: {v.gain_db:+.1f} dB"
                         + (f", tốc độ {v.speed:.3f}" if isinstance(stream, BedFromFiles) else "")
                         for v, stream, *_ in self.parts)


def mix_chunks(mixer: Mixer, total: int, loudness: float, sr=SR):
    """Yield the mix in chunks, scaled so the beds (or everything, without beds) sit at `loudness` LUFS."""
    chunk = int(rain.CHUNK_SECONDS * sr)
    produced = 0

    def chunks():
        nonlocal produced
        while produced < total:
            n = min(chunk, total - produced)
            produced += n
            yield mixer.read(n)

    stream = chunks()
    warmup, count = [], 0
    for item in stream:
        warmup.append(item)
        count += item[0].shape[1]
        if count >= min(total, rain.CALIBRATION_SECONDS * sr):
            break
    if not warmup:
        return
    measured = rain.loudness_lufs(np.concatenate([b for b, _ in warmup], axis=1), sr)
    if measured < -70:  # no beds: calibrate on everything
        measured = rain.loudness_lufs(np.concatenate([b + e for b, e in warmup], axis=1), sr)
    gain = np.float32(_gain_for(measured, loudness))
    for beds, events in itertools.chain(warmup, stream):
        yield (beds + events) * gain


def render_mix(recipe: Recipe, library: Library, seed: int, seconds: float, sink, progress=None, fade=None):
    total = int(round(seconds * SR))
    mixer = Mixer(recipe, library, seed, total)
    rain.finish(mix_chunks(mixer, total, recipe.loudness), total, sink, SR,
                recipe.fade if fade is None else fade, progress)
    library.save()
    return mixer


def preview_wav(recipe: Recipe, library: Library, seed: int, seconds: float) -> tuple[bytes, list[str]]:
    chunks = []
    mixer = render_mix(recipe, library, seed, seconds, chunks.append, fade=0.3)
    audio = np.concatenate(chunks, axis=1) if chunks else np.zeros((2, 1), np.float32)
    pcm = (np.clip(audio, -1, 1).T * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)
    return buf.getvalue(), mixer.warnings


def run_mix_job(job: dict) -> dict:
    """Render one mix to a file (or into a video). Top-level so it can run in a worker process."""
    started = time.time()
    recipe = Recipe.from_dict(job["recipe"])
    library = Library(job["library"])
    out = Path(job["output"])
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".part" + out.suffix)
    video = Path(job["video"]) if job.get("video") else None
    sink = rain.FFmpegSink(tmp, video=video)
    try:
        mixer = render_mix(recipe, library, job["seed"], job["seconds"], sink.write, job.get("progress"))
        sink.close()
    except BaseException:
        sink.abort()
        tmp.unlink(missing_ok=True)
        raise
    tmp.replace(out)
    return {"file": out.name, "seed": job["seed"], "recipe": recipe.name, "variation": recipe.variation,
            "seconds": round(job["seconds"], 3), "video": str(video or ""), "layers": mixer.summary(),
            "warnings": " | ".join(mixer.warnings), "render_seconds": round(time.time() - started, 1)}


# ---------------------------------------------------------------- command line

def make_jobs(recipe: Recipe, library: Library, seed0: int, outputs: list[tuple[Path, float, Path | None]], overwrite: bool):
    jobs = []
    for i, (out, seconds, video) in enumerate(outputs):
        if out.exists() and not overwrite:
            print(f"Bỏ qua (đã có): {out.name}")
            continue
        jobs.append({"recipe": recipe.to_dict(), "library": str(library.root), "seed": seed0 + i,
                     "seconds": seconds, "output": str(out), "video": str(video) if video else None})
    return jobs


def cmd_render(args):
    recipe, library = _load(args)
    seed = rain.base_seed(args)

    def progress(frac):
        print(f"\r  {frac * 100:5.1f}%", end="", file=sys.stderr, flush=True)

    row = run_mix_job({"recipe": recipe.to_dict(), "library": str(library.root), "seed": seed,
                       "seconds": args.duration, "output": args.output, "progress": progress})
    print(file=sys.stderr)
    print(f"Đã tạo {args.output}  seed={seed}  ({row['render_seconds']}s)")
    print(f"Các lớp: {row['layers']}")
    return 0


def cmd_batch(args):
    recipe, library = _load(args)
    outdir = Path(args.outdir)
    seed0 = rain.base_seed(args)
    slug = slugify(recipe.name)
    outputs = [(outdir / f"{slug}_{i + 1:04d}_s{seed0 + i}.{args.format}", args.duration, None) for i in range(args.count)]
    return rain.run_jobs(make_jobs(recipe, library, seed0, outputs, args.overwrite), args.jobs,
                         outdir / "manifest.csv", run_mix_job)


def cmd_video(args):
    recipe, library = _load(args)
    outdir = Path(args.outdir)
    seed0 = rain.base_seed(args)
    outputs, failed = [], 0
    for video in rain.find_videos(args.inputs):
        try:
            seconds = rain.media_duration(video)
        except RuntimeError as e:
            failed += 1
            print(f"LỖI {e}", file=sys.stderr)
            continue
        ext = ".webm" if video.suffix.lower() == ".webm" else ".mp4"
        outputs.append((outdir / f"{video.stem}{args.suffix}{ext}", seconds, video))
    code = rain.run_jobs(make_jobs(recipe, library, seed0, outputs, args.overwrite), args.jobs,
                         outdir / "manifest.csv", run_mix_job)
    return code or (1 if failed else 0)


def _load(args):
    recipe, _ = load_recipe(args.recipe, Path(args.recipes))
    if args.loudness is not None:
        recipe.loudness = args.loudness
    if args.variation is not None:
        recipe.variation = args.variation
    library = Library(args.library)
    for warning in library.prepare(recipe):
        print(f"Cảnh báo: {warning}", file=sys.stderr)
    return recipe, library


def cmd_studio(args):
    import studio

    return studio.serve(Path(args.library), Path(args.recipes), Path(args.outdir), args.port, not args.no_browser)


def build_parser():
    paths = argparse.ArgumentParser(add_help=False)
    paths.add_argument("--library", default="library", help="thư mục thư viện âm thanh (mặc định: library)")
    paths.add_argument("--recipes", default="recipes", help="thư mục công thức (mặc định: recipes)")

    common = argparse.ArgumentParser(add_help=False, parents=[paths])
    common.add_argument("recipe", help="tên công thức trong thư mục recipes, hoặc đường dẫn file .json")
    common.add_argument("-s", "--seed", type=int, help="seed bắt đầu (mặc định: ngẫu nhiên)")
    common.add_argument("--loudness", type=float, help="ghi đè độ lớn tổng của công thức, LUFS")
    common.add_argument("-v", "--variation", type=float, help="ghi đè mức khác nhau giữa các bản")

    parser = argparse.ArgumentParser(description="Rain Mixer: trộn các lớp tiếng mưa, mỗi seed một bản khác nhau.")
    sub = parser.add_subparsers(dest="command", required=True)

    st = sub.add_parser("studio", parents=[paths], help="mở giao diện mix trên trình duyệt")
    st.add_argument("--outdir", default="output", help="thư mục xuất file (mặc định: output)")
    st.add_argument("--port", type=int, default=8765)
    st.add_argument("--no-browser", action="store_true", help="không tự mở trình duyệt")
    st.set_defaults(func=cmd_studio)

    r = sub.add_parser("render", parents=[common], help="xuất một bản")
    r.add_argument("-d", "--duration", type=rain.parse_duration, default=600.0, help="độ dài (mặc định: 10m)")
    r.add_argument("-o", "--output", required=True, help="file đầu ra: .flac .wav .mp3 .m4a .ogg .opus")
    r.set_defaults(func=cmd_render)

    b = sub.add_parser("batch", parents=[common], help="xuất nhiều bản khác nhau")
    b.add_argument("-n", "--count", type=int, required=True)
    b.add_argument("-d", "--duration", type=rain.parse_duration, required=True)
    b.add_argument("--outdir", default="output")
    b.add_argument("--format", default="flac", choices=[e.lstrip(".") for e in rain.AUDIO_CODECS])
    b.add_argument("-j", "--jobs", type=int, default=1, help="số bản xuất song song")
    b.add_argument("--overwrite", action="store_true")
    b.set_defaults(func=cmd_batch)

    v = sub.add_parser("video", parents=[common], help="ghép một bản mix riêng vào từng video")
    v.add_argument("inputs", nargs="+", help="file video hoặc thư mục chứa video")
    v.add_argument("--outdir", default="output")
    v.add_argument("--suffix", default="_rain")
    v.add_argument("-j", "--jobs", type=int, default=1)
    v.add_argument("--overwrite", action="store_true")
    v.set_defaults(func=cmd_video)
    return parser


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    missing = [tool for tool in ("ffmpeg", "ffprobe") if not shutil.which(tool)]
    if missing:
        raise SystemExit(f"Cần cài {' và '.join(missing)} (https://ffmpeg.org/download.html)")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
