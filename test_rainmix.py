import io
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import wave
from http.server import ThreadingHTTPServer
from pathlib import Path

import numpy as np

import rain
import rainmix
import studio

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
SR = rainmix.SR


def write_wav(path: Path, x: np.ndarray, sr=SR):
    x = np.atleast_2d(x)
    if x.shape[0] == 1:
        x = np.vstack([x, x])
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1).T * 32767).astype("<i2").tobytes())


def make_library(root: Path):
    """Two noise beds (flac and a mono 44.1 kHz mp3) and a folder of short one-shots."""
    rng = np.random.default_rng(0)
    (root / "nen").mkdir(parents=True)
    (root / "giot").mkdir()
    write_wav(root / "a.wav", rng.standard_normal((2, SR * 40)) * 0.05)
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(root / "a.wav"), str(root / "nen" / "a.flac")], check=True)
    (root / "a.wav").unlink()
    write_wav(root / "b.wav", rng.standard_normal((2, SR * 25)) * 0.2)
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(root / "b.wav"), "-ac", "1", "-ar", "44100",
                    str(root / "nen" / "b.mp3")], check=True)
    (root / "b.wav").unlink()
    for i in range(3):
        click = np.zeros(SR // 2)
        click[1000:1400] = np.hanning(400) * 0.5
        write_wav(root / "giot" / f"g{i}.wav", click)


def recipe(*layers, **kwargs):
    return rainmix.Recipe(layers=[rainmix.Layer(**layer) for layer in layers], **kwargs)


def render_array(rec, library, seed, seconds, fade=None):
    chunks = []
    mixer = rainmix.render_mix(rec, library, seed, seconds, chunks.append, fade=fade)
    return np.concatenate(chunks, axis=1), mixer


class RecipeTest(unittest.TestCase):
    def test_round_trip_ignores_unknown_keys(self):
        data = {"name": "Thử", "loudness": -20, "junk": 1,
                "layers": [{"name": "A", "source": "synth:light", "gain_db": -3, "whatever": True}]}
        rec = rainmix.Recipe.from_dict(data)
        self.assertEqual(rec.loudness, -20)
        self.assertEqual(rec.layers[0].gain_db, -3)
        self.assertEqual(rec.layers[0].width, 1.0)
        self.assertEqual(rainmix.Recipe.from_dict(rec.to_dict()), rec)

    def test_example_recipes_load(self):
        for path in Path(__file__).with_name("recipes").glob("*.json"):
            rec = rainmix.Recipe.from_dict(json.loads(path.read_text(encoding="utf-8")))
            self.assertTrue(rec.layers, path.name)
            for layer in rec.layers:
                kind = rainmix.synth_kind(layer.source)
                if kind:
                    self.assertTrue(kind in rain.PRESETS or kind in rainmix.SYNTH_EVENTS, layer.source)

    def test_slugify(self):
        self.assertEqual(rainmix.slugify("Mưa mái tôn đêm khuya"), "mua_mai_ton_dem_khuya")
        self.assertEqual(rainmix.slugify("  ?? "), "cong_thuc")

    def test_vary_layer(self):
        layer = rainmix.Layer(source="x", gain_db=-6, lowpass_hz=19000, speed=1.0, width=1.9)
        self.assertEqual(rainmix.vary_layer(layer, 0, np.random.default_rng(1)), layer)
        a = rainmix.vary_layer(layer, 0.15, np.random.default_rng(1))
        self.assertEqual(a, rainmix.vary_layer(layer, 0.15, np.random.default_rng(1)))
        self.assertLessEqual(abs(a.gain_db + 6), 1.5 + 1e-9)
        self.assertLessEqual(a.lowpass_hz, 20000)
        self.assertLessEqual(a.width, 2.0)
        self.assertLess(abs(a.speed - 1), 0.031)

    def test_event_detection(self):
        self.assertTrue(rainmix.Layer(source="synth:thunder", type="bed").is_events)
        self.assertFalse(rainmix.Layer(source="synth:roof", type="events").is_events)
        self.assertTrue(rainmix.Layer(source="sam", type="events").is_events)


class SynthOnlyTest(unittest.TestCase):
    """Recipes that need no sound files."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.library = rainmix.Library(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_deterministic_length_and_loudness(self):
        rec = recipe({"source": "synth:light", "swell_db": 0},
                     {"source": "synth:drip", "per_minute": 30, "gain_db": -10}, loudness=-21)
        y, mixer = render_array(rec, self.library, 4, 12.5, fade=0)
        self.assertEqual(y.shape, (2, round(12.5 * SR)))
        self.assertEqual(len(mixer.parts), 2)
        np.testing.assert_array_equal(y, render_array(rec, self.library, 4, 12.5, fade=0)[0])
        self.assertFalse(np.allclose(y, render_array(rec, self.library, 5, 12.5, fade=0)[0]))
        self.assertAlmostEqual(rain.loudness_lufs(y.astype(np.float64), SR), -21, delta=1.5)
        self.assertLessEqual(float(np.abs(y).max()), 0.89 + 1e-6)

    def test_missing_source_warns_and_continues(self):
        rec = recipe({"name": "Mất", "source": "khong_co"}, {"source": "synth:medium"})
        y, mixer = render_array(rec, self.library, 1, 3)
        self.assertEqual(len(mixer.parts), 1)
        self.assertTrue(any("'Mất'" in w for w in mixer.warnings))
        self.assertGreater(float(np.abs(y).max()), 0.01)

    def test_disabled_and_empty(self):
        rec = recipe({"source": "synth:medium", "enabled": False})
        y, mixer = render_array(rec, self.library, 1, 2)
        self.assertEqual(mixer.parts, [])
        self.assertEqual(float(np.abs(y).max()), 0.0)

    def test_eq_on_synth_layer(self):
        bright = render_array(recipe({"source": "synth:medium", "swell_db": 0}), self.library, 2, 6, fade=0)[0]
        dark = render_array(recipe({"source": "synth:medium", "swell_db": 0, "lowpass_hz": 1500}), self.library, 2, 6, fade=0)[0]

        def high_share(x):
            p = np.abs(np.fft.rfft(x[0])) ** 2
            f = np.fft.rfftfreq(x.shape[1], 1 / SR)
            return p[f > 5000].sum() / p.sum()

        self.assertLess(high_share(dark), high_share(bright) / 4)

    def test_preview_wav(self):
        data, warnings = rainmix.preview_wav(recipe({"source": "synth:roof_light"}), self.library, 3, 4)
        with wave.open(io.BytesIO(data)) as w:
            self.assertEqual((w.getnchannels(), w.getframerate(), w.getnframes()), (2, SR, 4 * SR))
        self.assertEqual(warnings, [])


@unittest.skipUnless(HAS_FFMPEG, "cần ffmpeg")
class FileLayersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name) / "lib"
        make_library(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_library_scan_and_cache(self):
        lib = rainmix.Library(self.root)
        self.assertEqual(sorted(lib.folders()), ["giot", "nen"])
        self.assertEqual(lib.files("nen"), ["nen/a.flac", "nen/b.mp3"])
        self.assertEqual(lib.files("nen/a.flac"), ["nen/a.flac"])
        info = lib.info("nen/b.mp3")
        self.assertAlmostEqual(info["duration"], 25, delta=0.2)
        self.assertGreater(info["loudness"], -40)
        lib.save()
        cached = json.loads((self.root / rainmix.CACHE_FILE).read_text(encoding="utf-8"))
        self.assertIn("nen/b.mp3", cached)
        self.assertIn("loudness", rainmix.Library(self.root).cache["nen/b.mp3"])
        with self.assertRaises(ValueError):
            lib.resolve("../outside.wav")
        self.assertEqual(lib.files("../"), [])

    def test_bed_joins_keep_level(self):
        lib = rainmix.Library(self.root)
        layer = rainmix.Layer(source="nen", swell_db=0)
        bed = rainmix.BedFromFiles(np.random.default_rng(2), lib, lib.files("nen"), layer)
        x = np.concatenate([bed.read(SR * 2) for _ in range(90)], axis=1)  # 3 minutes, several joins
        frames = x[:, : x.shape[1] // 4800 * 4800].reshape(2, -1, 4800)
        level = 10 * np.log10(np.mean(frames ** 2, axis=(0, 2)))
        # Both files are normalised to the same loudness, so every 100 ms stays near the median.
        self.assertLess(float(np.max(np.abs(level - np.median(level)))), 2.0)

    def test_speed_changes_pitch(self):
        lib = rainmix.Library(self.root)
        tone = Path(self.tmp.name) / "tone"
        tone.mkdir(exist_ok=True)
        t = np.arange(SR * 4) / SR
        write_wav(tone / "t.wav", 0.3 * np.sin(2 * np.pi * 1000 * t))
        x = rainmix.decode(tone / "t.wav", speed=1.1)
        f = np.fft.rfftfreq(x.shape[1], 1 / SR)
        self.assertAlmostEqual(float(f[np.argmax(np.abs(np.fft.rfft(x[0])))]), 1100, delta=5)
        self.assertAlmostEqual(x.shape[1] / SR, 4 / 1.1, delta=0.02)

    def test_events_rate_and_mix(self):
        lib = rainmix.Library(self.root)
        layer = rainmix.Layer(source="giot", type="events", per_minute=30, min_gap_seconds=0)
        calls = []
        make = rainmix.file_event_maker(lib, lib.files("giot"), layer)
        events = rainmix.Events(np.random.default_rng(3), layer, lambda rng: calls.append(1) or make(rng))
        for _ in range(300):  # 10 minutes
            events.read(SR * 2)
        self.assertTrue(220 <= len(calls) <= 380, len(calls))

        rec = recipe({"source": "nen", "swell_db": 2}, {"source": "giot", "type": "events", "per_minute": 20},
                     {"source": "synth:thunder", "per_minute": 2})
        y, mixer = render_array(rec, lib, 7, 20)
        self.assertEqual(len(mixer.parts), 3)
        self.assertEqual(y.shape[1], 20 * SR)

    def test_broken_file_is_skipped_not_the_layer(self):
        root = Path(self.tmp.name) / "lib_broken"
        (root / "nen").mkdir(parents=True)
        write_wav(root / "nen" / "ok.wav", np.random.default_rng(1).standard_normal((2, SR * 5)) * 0.1)
        (root / "nen" / "hong.mp3").write_bytes(b"not audio at all")
        lib = rainmix.Library(root)
        y, mixer = render_array(recipe({"name": "Nền", "source": "nen"}), lib, 1, 8)
        self.assertEqual(len(mixer.parts), 1)
        self.assertTrue(any("hong.mp3" in w for w in mixer.warnings))
        self.assertGreater(float(np.abs(y).max()), 0.01)

    def test_cli_batch(self):
        out = Path(self.tmp.name) / "out"
        path = Path(self.tmp.name) / "r.json"
        rec = recipe({"source": "nen"}, {"source": "giot", "type": "events"}, name="Thử nghiệm")
        path.write_text(json.dumps(rec.to_dict(), ensure_ascii=False), encoding="utf-8")
        subprocess.run([sys.executable, "rainmix.py", "batch", str(path), "--library", str(self.root), "-n", "2",
                        "-d", "5s", "-s", "40", "--outdir", str(out), "--format", "flac"],
                       cwd=Path(__file__).parent, check=True, capture_output=True)
        files = sorted(p.name for p in out.glob("*.flac"))
        self.assertEqual(files, ["thu_nghiem_0001_s40.flac", "thu_nghiem_0002_s41.flac"])
        self.assertIn("Thử nghiệm", (out / "manifest.csv").read_text(encoding="utf-8"))


@unittest.skipUnless(HAS_FFMPEG, "cần ffmpeg")
class StudioApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        make_library(base / "lib")
        cls.recipes = base / "recipes"
        cls.recipes.mkdir()
        cls.app = studio.Studio(base / "lib", cls.recipes, base / "out")
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), studio.make_handler(cls.app))
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def request(self, path, body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, headers={"Content-Type": "application/json", **(headers or {})})
        return urllib.request.urlopen(req, timeout=60)

    def test_page_and_state(self):
        self.assertIn(b"Rain Mixer", self.request("/").read())
        state = json.loads(self.request("/api/state").read())
        folders = {f["name"]: f for f in state["library"]}
        self.assertEqual(folders["giot"]["suggested_type"], "events")
        self.assertEqual(folders["nen"]["suggested_type"], "bed")
        self.assertIn("synth:roof", [s["id"] for s in state["synth"]])

    def test_save_load_preview(self):
        rec = recipe({"name": "Nền", "source": "nen"}, {"name": "Thiếu", "source": "khong_co"}, name="Mưa thử").to_dict()
        saved = json.loads(self.request("/api/recipe", {"recipe": rec}).read())
        self.assertEqual(saved["name"], "mua_thu")
        self.assertEqual(json.loads(self.request("/api/recipe?name=mua_thu").read()), rec)
        res = self.request("/api/preview", {"recipe": rec, "seed": 3, "seconds": 3})
        info = json.loads(res.headers["X-Mix-Info"])
        self.assertTrue(any("Thiếu" in w for w in info["warnings"]))
        with wave.open(io.BytesIO(res.read())) as w:
            self.assertEqual(w.getnframes(), 3 * SR)

    def test_file_range_and_traversal(self):
        res = self.request("/api/file?path=giot/g0.wav", headers={"Range": "bytes=0-99"})
        self.assertEqual((res.status, len(res.read())), (206, 100))
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request("/api/file?path=../recipes")
        self.assertEqual(ctx.exception.code, 400)

    def test_export(self):
        rec = recipe({"source": "synth:light"}, name="Xuất").to_dict()
        job = json.loads(self.request("/api/export", {"recipe": rec, "count": 2, "duration": "3s", "format": "mp3", "seed": "9"}).read())
        for _ in range(600):
            jobs = {j["id"]: j for j in json.loads(self.request("/api/jobs").read())["jobs"]}
            if jobs[job["job"]]["status"] in ("done", "error"):
                break
            threading.Event().wait(0.1)
        self.assertEqual(jobs[job["job"]]["files"], ["xuat_0001_s9.mp3", "xuat_0002_s10.mp3"])
        with self.assertRaises(urllib.error.HTTPError):
            self.request("/api/export", {"recipe": rec, "duration": "abc"})


if __name__ == "__main__":
    unittest.main()
