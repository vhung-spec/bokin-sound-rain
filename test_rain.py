import argparse
import shutil
import subprocess
import sys
import tempfile
import unittest
from dataclasses import fields
from pathlib import Path

import numpy as np

import rain

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def render_array(params, seed, seconds, **kwargs):
    chunks = []
    rain.render(params, seed, seconds, chunks.append, **kwargs)
    return np.concatenate(chunks, axis=1)


class ParseTest(unittest.TestCase):
    def test_durations(self):
        cases = {"90": 90, "90s": 90, "10m": 600, "1h": 3600, "1h30m": 5400, "1.5h": 5400,
                 "01:30:00": 5400, "2:30": 150, "1m30s": 90}
        for text, seconds in cases.items():
            self.assertAlmostEqual(rain.parse_duration(text), seconds, msg=text)
        for text in ("", "abc", "0", "-5", "10x"):
            with self.assertRaises(argparse.ArgumentTypeError, msg=text):
                rain.parse_duration(text)

    def test_presets(self):
        self.assertEqual(rain.parse_presets("light, heavy"), ["light", "heavy"])
        self.assertEqual(rain.parse_presets("all"), list(rain.PRESETS))
        with self.assertRaises(argparse.ArgumentTypeError):
            rain.parse_presets("snow")


class VariationTest(unittest.TestCase):
    def test_zero_variation_keeps_preset(self):
        name, params = rain.pick_params(["medium"], 0.0, 123)
        self.assertEqual(params, rain.PRESETS["medium"][1])

    def test_variation_is_bounded_and_reproducible(self):
        base = rain.PRESETS["storm"][1]
        a = rain.pick_params(["storm"], 0.15, 9)[1]
        self.assertEqual(a, rain.pick_params(["storm"], 0.15, 9)[1])
        self.assertNotEqual(a, rain.pick_params(["storm"], 0.15, 10)[1])
        for f in fields(base):
            old, new = getattr(base, f.name), getattr(a, f.name)
            if isinstance(old, str):
                self.assertEqual(old, new)
            elif f.name in rain.BOUNDED:
                self.assertTrue(0 <= new <= 1 and abs(new - old) <= 0.075 + 1e-9, f.name)
            elif old:
                self.assertTrue(np.exp(-0.15) - 1e-9 <= new / old <= np.exp(0.15) + 1e-9, f.name)

    def test_band_edges_stay_ordered(self):
        for seed in range(50):
            p = rain.pick_params(["light"], 2.0, seed)[1]
            self.assertLess(p.hiss_low_hz, p.hiss_high_hz)
            self.assertLess(p.drop_low_hz, p.drop_high_hz)


class RenderTest(unittest.TestCase):
    def test_noise_has_unit_variance(self):
        for texture in (0.0, 0.5):
            noise = rain.ShapedNoise(np.random.default_rng(1), 48000, lambda f: rain.band(f, 600, 9000, 0.25),
                                     texture=texture, texture_rate=1500)
            self.assertAlmostEqual(float(noise.read(48000 * 10).std()), 1.0, delta=0.05)

    def test_same_seed_same_audio_different_seed_different_audio(self):
        p = rain.PRESETS["storm"][1]
        a = render_array(p, 5, 3.0)
        self.assertEqual(a.shape, (2, 3 * 48000))
        np.testing.assert_array_equal(a, render_array(p, 5, 3.0))
        self.assertFalse(np.allclose(a, render_array(p, 6, 3.0)))

    def test_odd_length_and_peak_ceiling(self):
        for name in rain.PRESETS:
            y = render_array(rain.PRESETS[name][1], 1, 2.345)
            self.assertEqual(y.shape[1], round(2.345 * 48000))
            self.assertLessEqual(float(np.abs(y).max()), 0.89 + 1e-6, name)

    def test_loudness_hits_target(self):
        for name in ("light", "roof"):
            y = render_array(rain.PRESETS[name][1], 3, 20.0, fade=0, loudness=-20.0)
            self.assertAlmostEqual(rain.loudness_lufs(y.astype(np.float64), 48000), -20.0, delta=1.5, msg=name)


@unittest.skipUnless(HAS_FFMPEG, "cần ffmpeg")
class CliTest(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "rain.py", *args], cwd=Path(__file__).parent,
                              capture_output=True, text=True, check=True)

    def duration(self, path):
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                              "default=nw=1:nk=1", str(path)], capture_output=True, text=True, check=True)
        return float(out.stdout)

    def test_batch_and_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self.run_cli("batch", "-p", "light,roof", "-n", "3", "-d", "4s", "-s", "10", "--outdir", str(tmp / "a"))
            files = sorted((tmp / "a").glob("*.flac"))
            self.assertEqual(len(files), 3)
            for i, f in enumerate(files):
                preset = rain.pick_params(["light", "roof"], 0.15, 10 + i)[0]
                self.assertEqual(f.name, f"rain_{i + 1:04d}_{preset}_s{10 + i}.flac")
                self.assertAlmostEqual(self.duration(f), 4.0, delta=0.01)
            again = self.run_cli("batch", "-p", "light,roof", "-n", "1", "-d", "4s", "-s", "10", "--outdir", str(tmp / "a"))
            self.assertIn("Bỏ qua", again.stdout)

            video = tmp / "clip.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=160x90:d=5",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)], check=True)
            self.run_cli("video", str(video), "--outdir", str(tmp / "v"), "-s", "3")
            out = tmp / "v" / "clip_rain.mp4"
            self.assertAlmostEqual(self.duration(out), 5.0, delta=0.1)
            lines = (tmp / "v" / "manifest.csv").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            self.assertTrue(lines[1].startswith("clip_rain.mp4,3,medium,"))


if __name__ == "__main__":
    unittest.main()
