import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

from core.tts import group_sentences, join_audio_segments, save_wav, split_sentences


class SentenceGroupingTests(unittest.TestCase):
    def test_related_short_sentences_share_a_segment(self):
        sentences = ["Bonjour.", "Comment vas-tu ?", "À bientôt !"]

        self.assertEqual(group_sentences(sentences, 240), [
            "Bonjour. Comment vas-tu ? À bientôt !",
        ])

    def test_grouping_splits_only_between_sentences(self):
        sentences = ["Première phrase.", "Deuxième phrase.", "Une phrase qui dépasse largement la limite."]

        self.assertEqual(group_sentences(sentences, 40), [
            "Première phrase. Deuxième phrase.",
            "Une phrase qui dépasse largement la limite.",
        ])

    def test_non_positive_limit_keeps_all_sentences_together(self):
        self.assertEqual(group_sentences(["Une.", "Deux."], 0), ["Une. Deux."])

    def test_sentence_split_keeps_question_and_exclamation_boundaries(self):
        self.assertEqual(split_sentences("Tu viens ? Très bien ! Alors, on y va."),
                         ["Tu viens ?", "Très bien !", "Alors, on y va."])

    def test_wav_export_writes_mono_pcm_at_source_rate(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reference.wav"
            save_wav(path, [(np.array([0, 1, -1], dtype=np.int16), 24000)])

            with wave.open(str(path), "rb") as audio:
                self.assertEqual(audio.getnchannels(), 1)
                self.assertEqual(audio.getsampwidth(), 2)
                self.assertEqual(audio.getframerate(), 24000)
                self.assertEqual(audio.getnframes(), 3)

    def test_audio_segments_must_have_the_same_sample_rate(self):
        segments = [(np.array([0], dtype=np.int16), 24000),
                    (np.array([1], dtype=np.int16), 22050)]

        with self.assertRaisesRegex(ValueError, "fréquences différentes"):
            join_audio_segments(segments)


if __name__ == "__main__":
    unittest.main()
