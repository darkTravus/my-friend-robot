"""Text-to-speech local avec Piper (appelé en ligne de commande : robuste aux changements de version)."""
import os
import subprocess
import sys
import tempfile


class TTS:
    def __init__(self, model_path: str, audio):
        self.model_path, self.audio = model_path, audio
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"Voix Piper introuvable : {model_path}\n"
                "Télécharge-la (voir README, étape 4)."
            )

    def speak(self, text: str):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "speech.wav")
            subprocess.run(
                [sys.executable, "-m", "piper", "-m", self.model_path, "-f", out],
                input=text.encode("utf-8"), check=True, capture_output=True,
            )
            self.audio.play_wav(out)
