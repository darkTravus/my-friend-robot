import unittest

import numpy as np

from core.wake import OpenWakeWordDetector


class FakeWakeModel:
    def __init__(self, scores):
        self.scores = iter(scores)
        self.reset_count = 0

    def predict(self, pcm):
        return {"hey_zephyr": next(self.scores)}

    def reset(self):
        self.reset_count += 1


class WakeDetectorTests(unittest.TestCase):
    def make_detector(self, scores, threshold=0.75, need=3, minimum_rms=0.008):
        detector = OpenWakeWordDetector.__new__(OpenWakeWordDetector)
        detector.model = FakeWakeModel(scores)
        detector.threshold = threshold
        detector.need = need
        detector.minimum_rms = minimum_rms
        detector.hits = 0
        detector.last_score = 0.0
        return detector

    def test_requires_configured_number_of_consecutive_high_scores(self):
        detector = self.make_detector([0.9, 0.9, 0.9])
        block = np.full(1280, 0.02, dtype=np.float32)

        self.assertFalse(detector.process(block))
        self.assertFalse(detector.process(block))
        self.assertTrue(detector.process(block))
        self.assertEqual(detector.hits, 0)

    def test_low_score_resets_consecutive_hit_count(self):
        detector = self.make_detector([0.9, 0.9, 0.2, 0.9, 0.9, 0.9])
        block = np.full(1280, 0.02, dtype=np.float32)

        self.assertFalse(detector.process(block))
        self.assertFalse(detector.process(block))
        self.assertFalse(detector.process(block))
        self.assertFalse(detector.process(block))
        self.assertFalse(detector.process(block))
        self.assertTrue(detector.process(block))

    def test_quiet_audio_cannot_trigger_even_with_high_model_score(self):
        detector = self.make_detector([0.99, 0.99, 0.99])
        quiet_block = np.full(1280, 0.001, dtype=np.float32)

        self.assertFalse(detector.process(quiet_block))
        self.assertFalse(detector.process(quiet_block))
        self.assertFalse(detector.process(quiet_block))
        self.assertEqual(detector.hits, 0)

    def test_speech_level_audio_can_trigger_with_high_scores(self):
        detector = self.make_detector([0.9, 0.9, 0.9])
        speech_block = np.full(1280, 0.02, dtype=np.float32)

        self.assertFalse(detector.process(speech_block))
        self.assertFalse(detector.process(speech_block))
        self.assertTrue(detector.process(speech_block))

    def test_invalid_detector_settings_are_rejected(self):
        for threshold, need, minimum_rms in [
                (1.1, 3, 0.008),                 (0.75, 0, 0.008), (0.75, 3, -0.1)]:
            detector = OpenWakeWordDetector.__new__(OpenWakeWordDetector)
            detector.threshold = threshold
            detector.need = need
            detector.minimum_rms = minimum_rms
            with self.subTest(threshold=threshold, need=need, minimum_rms=minimum_rms):
                with self.assertRaises(ValueError):
                    detector._validate_settings()


if __name__ == "__main__":
    unittest.main()
