import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import numpy as np

from core.speaker import SpeakerIdentifier, SpeakerProfileStore


class FakeSession:
    def __init__(self, embedding):
        self.embedding = np.asarray(embedding, dtype=np.float32)

    @staticmethod
    def get_inputs():
        return [type("Input", (), {"name": "feats"})()]

    @staticmethod
    def get_outputs():
        return [type("Output", (), {"name": "embs"})()]

    def run(self, output_names, inputs):
        return [self.embedding.reshape(1, -1)]


def wav_bytes(seconds=4, sample_rate=16000):
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "sample.wav"
        with wave.open(str(path), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(sample_rate)
            audio.writeframes(np.zeros(seconds * sample_rate, dtype="<i2").tobytes())
        return path.read_bytes()


class SpeakerProfileTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.profile_path = Path(self.temporary_directory.name) / "profiles.json"
        self.store = SpeakerProfileStore(self.profile_path)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_profile_is_saved_locally_and_normalized(self):
        self.store.add("alice", "Alice", ["manga", "musique", "manga"], [3, 4])

        profile = self.store.load()["alice"]
        self.assertEqual(profile["display_name"], "Alice")
        self.assertEqual(profile["interests"], ["manga", "musique"])
        np.testing.assert_allclose(profile["embedding"], [0.6, 0.8])

    def test_profile_can_be_deleted(self):
        self.store.add("alice", "Alice", [], [1.0, 0.0])

        self.assertTrue(self.store.remove("alice"))
        self.assertFalse(self.store.remove("alice"))
        self.assertEqual(self.store.load(), {})

    def test_invalid_store_is_not_silently_replaced(self):
        self.profile_path.write_text("{bad json", encoding="utf-8")

        with self.assertRaises(json.JSONDecodeError):
            self.store.load()
        self.assertEqual(self.profile_path.read_text(encoding="utf-8"), "{bad json")

    def test_short_audio_is_unknown_without_running_inference(self):
        session = FakeSession([1.0, 0.0])
        self.store.add("alice", "Alice", [], [1.0, 0.0])
        identifier = SpeakerIdentifier(
            "unused.onnx", self.profile_path, session=session, minimum_duration=3.0
        )

        profile, reason, score = identifier.identify(wav_bytes(seconds=2))

        self.assertIsNone(profile)
        self.assertEqual(reason, "phrase trop courte")
        self.assertIsNone(score)
        session.run = unittest.mock.Mock(side_effect=AssertionError("inference should be skipped"))
        self.assertIsNone(identifier.identify(wav_bytes(seconds=2))[0])

    def test_identification_returns_only_the_best_profile_over_threshold(self):
        self.store.add("alice", "Alice", ["mangas"], [1.0, 0.0])
        self.store.add("bob", "Bob", [], [0.0, 1.0])
        identifier = SpeakerIdentifier(
            "unused.onnx", self.profile_path, session=FakeSession([1.0, 0.0])
        )
        with patch("core.speaker.compute_fbank", return_value=np.ones((2, 80), dtype=np.float32)):
            profile, reason, score = identifier.identify(wav_bytes())

        self.assertEqual(profile["display_name"], "Alice")
        self.assertEqual(profile["interests"], ["mangas"])
        self.assertEqual(reason, "identifié")
        self.assertAlmostEqual(score, 1.0)

    def test_low_score_and_ambiguous_match_are_unknown(self):
        self.store.add("alice", "Alice", [], [1.0, 0.0])
        self.store.add("bob", "Bob", [], [0.0, 1.0])
        identifier = SpeakerIdentifier(
            "unused.onnx", self.profile_path, session=FakeSession([-1.0, 0.0])
        )
        with patch("core.speaker.compute_fbank", return_value=np.ones((2, 80), dtype=np.float32)):
            profile, reason, _ = identifier.identify(wav_bytes())
        self.assertIsNone(profile)
        self.assertEqual(reason, "score sous le seuil")

        self.store.remove("bob")
        self.store.add("bob", "Bob", [], [0.999, 0.04])
        identifier = SpeakerIdentifier(
            "unused.onnx", self.profile_path, session=FakeSession([1.0, 0.0])
        )
        with patch("core.speaker.compute_fbank", return_value=np.ones((2, 80), dtype=np.float32)):
            profile, reason, _ = identifier.identify(wav_bytes())
        self.assertIsNone(profile)
        self.assertEqual(reason, "profils trop proches")

    def test_single_profile_is_not_enough_to_identify_unknown_people(self):
        self.store.add("alice", "Alice", [], [1.0, 0.0])
        identifier = SpeakerIdentifier(
            "unused.onnx", self.profile_path, session=FakeSession([1.0, 0.0])
        )
        with patch("core.speaker.compute_fbank", return_value=np.ones((2, 80), dtype=np.float32)):
            profile, reason, score = identifier.identify(wav_bytes())

        self.assertIsNone(profile)
        self.assertEqual(reason, "au moins deux profils requis")
        self.assertIsNone(score)

    def test_enrollment_requires_three_long_recordings_and_saves_no_audio(self):
        identifier = SpeakerIdentifier(
            "unused.onnx", self.profile_path, session=FakeSession([1.0, 0.0])
        )
        recordings = [wav_bytes() for _ in range(3)]
        with patch("core.speaker.compute_fbank", return_value=np.ones((2, 80), dtype=np.float32)):
            identifier.enroll("alice", "Alice", ["lecture"], recordings)

        self.assertTrue(self.profile_path.is_file())
        self.assertEqual(set(self.profile_path.parent.iterdir()), {self.profile_path})
        self.assertEqual(identifier.store.load()["alice"]["interests"], ["lecture"])
        with self.assertRaisesRegex(ValueError, "au moins trois"):
            identifier.enroll("bob", "Bob", [], recordings[:2])


if __name__ == "__main__":
    unittest.main()
