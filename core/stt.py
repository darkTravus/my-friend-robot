"""Speech-to-text : audio -> texte, via une API compatible OpenAI (Whisper)."""
from openai import OpenAI


class STT:
    def __init__(self, client: OpenAI, model: str, language: str):
        self.client, self.model, self.language = client, model, language

    def transcribe(self, wav_bytes: bytes) -> str:
        result = self.client.audio.transcriptions.create(
            model=self.model,
            file=("audio.wav", wav_bytes, "audio/wav"),
            language=self.language,
        )
        return result.text.strip()
