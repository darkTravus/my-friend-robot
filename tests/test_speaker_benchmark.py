import importlib.util
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

from scripts.benchmark_speakers import (
    compute_fbank,
    identification_metrics,
    load_wav,
    make_profile,
    score_test_embeddings,
    threshold_metrics,
)


class SpeakerBenchmarkTests(unittest.TestCase):
    def test_load_wav_accepts_project_format(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "voice.wav"
            samples = np.array([0, 100, -100], dtype="<i2")
            with wave.open(str(path), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(16000)
                audio.writeframes(samples.tobytes())

            loaded, duration = load_wav(path)

            np.testing.assert_array_equal(loaded, samples.astype(np.float32))
            self.assertAlmostEqual(duration, 3 / 16000)

    def test_load_wav_rejects_wrong_sample_rate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "voice.wav"
            with wave.open(str(path), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(24000)
                audio.writeframes(np.array([1], dtype="<i2").tobytes())

            with self.assertRaisesRegex(ValueError, "16000 Hz"):
                load_wav(path)

    def test_profile_is_normalized_mean_of_enrollment_embeddings(self):
        profile = make_profile([
            np.array([1.0, 0.0]),
            np.array([0.8, 0.2]),
        ])

        self.assertAlmostEqual(float(np.linalg.norm(profile)), 1.0)
        self.assertGreater(profile[0], profile[1])

    def test_separate_test_embeddings_produce_genuine_impostor_and_top_one_scores(self):
        profiles = {
            "a": make_profile([np.array([1.0, 0.0]), np.array([0.99, 0.01])]),
            "b": make_profile([np.array([0.0, 1.0]), np.array([0.01, 0.99])]),
        }

        genuine, impostor, predictions = score_test_embeddings(profiles, [
            ("a", np.array([1.0, 0.0])),
            ("b", np.array([0.0, 1.0])),
        ])

        self.assertEqual(len(genuine), 2)
        self.assertEqual(len(impostor), 2)
        self.assertTrue(all(true == predicted for true, predicted, _ in predictions))
        self.assertGreater(min(genuine), max(impostor))

    def test_threshold_metrics_count_false_accepts_and_rejects(self):
        metrics = threshold_metrics([0.8, 0.2], [0.3, 0.1], 0.25)

        self.assertEqual(metrics["false_rejects"], 1)
        self.assertEqual(metrics["genuine_count"], 2)
        self.assertEqual(metrics["false_accepts"], 1)
        self.assertEqual(metrics["impostor_count"], 2)
        self.assertEqual(metrics["false_reject_rate"], 0.5)
        self.assertEqual(metrics["false_accept_rate"], 0.5)

    def test_identification_metrics_count_wrong_matches_and_rejections(self):
        metrics = identification_metrics([
            ("a", "a", 0.8),
            ("b", "a", 0.7),
            ("a", "a", 0.1),
        ], 0.5)

        self.assertEqual(metrics["correct_identifications"], 1)
        self.assertEqual(metrics["false_identifications"], 1)
        self.assertEqual(metrics["rejected"], 1)
        self.assertEqual(metrics["total"], 3)

    def test_profile_requires_multiple_enrollment_samples(self):
        with self.assertRaisesRegex(ValueError, "au moins deux extraits"):
            make_profile([np.array([1.0, 0.0])])

    @unittest.skipUnless(importlib.util.find_spec("kaldi_native_fbank"),
                         "dépendance optionnelle kaldi-native-fbank absente")
    def test_fbank_returns_80_mel_bins(self):
        samples = np.sin(np.arange(8000, dtype=np.float32) * (2 * np.pi * 220 / 16000)) * 1000

        features = compute_fbank(samples)

        self.assertEqual(features.shape[1], 80)
        self.assertTrue(np.isfinite(features).all())


if __name__ == "__main__":
    unittest.main()
