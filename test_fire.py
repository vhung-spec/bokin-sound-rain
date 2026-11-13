import subprocess
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

import numpy as np

import fire
import rain
from test_rain import HAS_FFMPEG


def mix(params, seed, seconds, **kwargs):
    total = int(seconds * fire.SR)
    return np.concatenate(list(fire.fire_chunks(params, seed, total, **kwargs)), axis=1)


class ParamsTest(unittest.TestCase):
    def test_vary_is_deterministic_and_bounded(self):
        base = fire.PRESETS["campfire"][1]
        a = fire.pick_params(["campfire"], 0.15, 5)[1]
        b = fire.pick_params(["campfire"], 0.15, 5)[1]
        self.assertEqual(a, b)
        self.assertNotEqual(a, fire.pick_params(["campfire"], 0.15, 6)[1])
        self.assertEqual(fire.pick_params(["campfire"], 0.0, 5)[1], base)
        for name, value in asdict(a).items():
            ref = getattr(base, name)
            if ref > 0:
                self.assertLess(abs(np.log(value / ref)), 0.5, name)
        self.assertLess(a.crackle_branch, 0.9)  # the crackle clusters must stay finite


class SynthTest(unittest.TestCase):
    def test_every_preset_renders_at_target_loudness(self):
        for name in fire.PRESETS:
            params = fire.pick_params([name], 0.15, 3)[1]
            y = mix(params, 3, 20)
            self.assertEqual(y.shape, (2, 20 * fire.SR), name)
            self.assertTrue(np.isfinite(y).all(), name)
            self.assertLessEqual(float(np.abs(y).max()), 0.68 + 1e-4, name)
            self.assertAlmostEqual(rain.loudness_lufs(y, fire.SR), -20.0, delta=1.5, msg=name)

    def test_same_seed_same_audio_and_seeds_differ(self):
        params = fire.PRESETS["crackling"][1]
        a, b, c = mix(params, 1, 8), mix(params, 1, 8), mix(params, 2, 8)
        np.testing.assert_array_equal(a, b)
        self.assertLess(abs(np.corrcoef(a[0], c[0])[0, 1]), 0.1)

    def test_chunk_size_does_not_matter_for_length(self):
        params = fire.PRESETS["embers"][1]
        y = mix(params, 4, 5.37)
        self.assertEqual(y.shape[1], int(5.37 * fire.SR))


class LimiterTest(unittest.TestCase):
    def test_spikes_at_chunk_borders_are_caught_and_quiet_audio_is_untouched(self):
        rng = np.random.default_rng(0)
        x = (rng.standard_normal((2, 48000 * 3)) * 0.05).astype(np.float32)
        spikes = [47999, 48000, 48001, 100000, x.shape[1] - 1]
        x[:, spikes] = 3.0
        chunks = [x[:, i:i + 48000] for i in range(0, x.shape[1], 48000)]
        y = np.concatenate(list(fire.limit(iter(chunks), x.shape[1])), axis=1)
        self.assertEqual(y.shape, x.shape)
        self.assertLessEqual(float(np.abs(y).max()), 0.68 + 1e-6)
        far = np.ones(x.shape[1], bool)
        for k in spikes:
            far[max(0, k - 200):k + 200] = False
        np.testing.assert_allclose(y[:, far], x[:, far], rtol=1e-6)


@unittest.skipUnless(HAS_FFMPEG, "cần ffmpeg")
class RealMixTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.lib = Path(self.tmp.name) / "library"
        (self.lib / "lua").mkdir(parents=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "anoisesrc=c=brown:r=48000:a=0.3:d=40",
                        "-af", "lowpass=f=300", "-ac", "2", str(self.lib / "lua" / "nen.flac")], check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_real_layer_is_mixed_quietly_and_reproducibly(self):
        library, files = fire.real_files(str(self.lib), "lua")
        real = (library, files, "lua")
        params = fire.PRESETS["campfire"][1]
        dry = mix(params, 7, 12)
        a = mix(params, 7, 12, real=real, real_db=-6.0)
        b = mix(params, 7, 12, real=real, real_db=-6.0)
        loud = mix(params, 7, 12, real=real, real_db=6.0)
        np.testing.assert_array_equal(a, b)
        # the stand-in recording is a low rumble: the more of it, the less the mix resembles the dry synth
        corr = [np.corrcoef(dry[0], x[0])[0, 1] for x in (a, loud)]
        self.assertGreater(corr[0], corr[1])
        self.assertLess(corr[0], 0.999)
        self.assertAlmostEqual(rain.loudness_lufs(a, fire.SR), -20.0, delta=1.5)

    def test_cli_batch_writes_files_and_manifest(self):
        out = Path(self.tmp.name) / "out"
        code = fire.main(["batch", "-p", "campfire,fireplace", "-n", "2", "-d", "6s", "-s", "3",
                          "--real", "lua", "--library", str(self.lib), "--outdir", str(out)])
        self.assertEqual(code, 0)
        self.assertEqual(len(list(out.glob("fire_*.flac"))), 2)
        manifest = (out / "manifest.csv").read_text(encoding="utf-8")
        self.assertIn("real_db", manifest.splitlines()[0])
        self.assertIn(",lua,", manifest)


if __name__ == "__main__":
    unittest.main()
