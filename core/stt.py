"""Speech-to-text : audio -> texte, via une API compatible OpenAI (Whisper)."""
from openai import OpenAI

_REPL = {"\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-",
         "’": "'", "‘": "'", "«": "", "»": ""}


def _plain(s: str) -> str:
    for a, b in _REPL.items():
        s = s.replace(a, b)
    return " ".join(s.split())


class STT:
    def __init__(self, client: OpenAI, model: str, language: str, prompt: str | None = None):
        self.client, self.model, self.language, self.prompt = client, model, language, prompt or ""

    def transcribe(self, wav_bytes: bytes, context: str = "") -> str:
        """context = dernière réponse du robot : aide Whisper à bien écrire les noms propres déjà cités."""
        prompt = self.prompt
        if context:
            prompt = f"{prompt} Contexte récent : {_plain(context)[-350:]}".strip()
        kwargs = {"prompt": prompt} if prompt else {}
        result = self.client.audio.transcriptions.create(
            model=self.model,
            file=("audio.wav", wav_bytes, "audio/wav"),
            language=self.language,
            temperature=0,
            **kwargs,
        )
        return _plain(result.text).strip('" ')
