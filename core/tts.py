"""Text-to-speech : voix neuronale en ligne (edge-tts, gratuite) ou Piper (local, hors-ligne).
La réponse est découpée en phrases : la 1re est lue pendant que la suivante est synthétisée."""
import asyncio
import os
import queue
import re
import threading
import time
import unicodedata

import numpy as np


def clean_for_speech(text: str) -> str:
    """Nettoie le texte pour la synthèse : markdown, listes, apostrophes, symboles."""
    text = unicodedata.normalize("NFC", text)
    for a, b in {"°C": " degrés", "°": " degrés", "km/h": " kilomètres par heure", "\u2011": "-", "\u2010": "-", "\u2012": "-", "’": "'", "‘": "'", "`": "'",
                 "“": '"', "”": '"', "«": "", "»": "", "…": "...", "–": ", ", "—": ", ",
                 "\u00a0": " ", "\u202f": " ", "%": " pour cent", "&": " et ",
                 "€": " euros", "$": " dollars", "*": "", "#": "", "_": " ", "~": ""}.items():
        text = text.replace(a, b)
    text = re.sub(r"\[[^\]]{1,20}\]", "", text)   # étiquettes d'émotion égarées : jamais lues
    # listes : on retire les puces et on termine chaque ligne par une ponctuation (= une pause)
    lines = []
    for line in text.splitlines():
        line = re.sub(r"^\s*([-•]|\d+[.)])\s+", "", line).strip()
        if line:
            lines.append(line if line[-1] in ".!?:;" else line + ".")
    text = re.sub(r"\s+", " ", " ".join(lines))
    return re.sub(r"\s+([,.;])", r"\1", text).strip()


def split_sentences(text: str):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


class TTS:
    """Plusieurs profils de voix (femme, homme...) ; changement possible à tout moment avec set_voice()."""

    def __init__(self, cfg: dict, audio):
        self.audio = audio
        self.engine = cfg.get("engine", "edge")
        self.edge_rate = cfg.get("edge_rate", "+0%")
        self.max_chars = int(cfg.get("max_spoken_chars", 0))  # 0 = pas de limite
        self.profiles = cfg["voices"]
        self.current = cfg.get("voice") or next(iter(self.profiles))
        if self.current not in self.profiles:
            self.current = next(iter(self.profiles))
        self._piper_cache = {}   # chemin du modèle -> voix Piper chargée
        self._piper_lock = threading.Lock()
        self._phrase_cache = {}  # (profil, phrase) -> audio pré-synthétisé (phrases d'attente)
        self._warned = False

        if self.engine == "edge":
            import edge_tts, miniaudio  # noqa: F401  (échoue tôt avec un message clair)
        piper_voice = self._piper_voice()
        if piper_voice is None and self.engine == "piper":
            raise FileNotFoundError(
                f"Voix Piper introuvable : {self.profile.get('piper')}\nVoir README, étape 4.")
        if piper_voice is not None:
            self._synth_piper("Bonjour.")  # échauffement

    # ---- profils -------------------------------------------------------
    @property
    def profile(self) -> dict:
        return self.profiles[self.current]

    def voice_names(self):
        return list(self.profiles)

    def set_voice(self, name: str) -> bool:
        if name not in self.profiles:
            return False
        self.current = name
        self._warned = False
        if self._piper_voice() is not None:
            self._synth_piper("Bonjour.")
        return True

    # ---- moteurs -------------------------------------------------------
    def _piper_voice(self):
        path = self.profile.get("piper")
        if not path or not os.path.exists(path):
            return None
        if path not in self._piper_cache:
            from piper import PiperVoice
            self._piper_cache[path] = PiperVoice.load(path)
        return self._piper_cache[path]

    def _synth_piper(self, text: str):
        """Retourne (tableau int16, fréquence). Gère piper-tts 1.2 et 1.3+."""
        voice = self._piper_voice()
        if voice is None:
            raise RuntimeError("Aucune voix Piper de secours pour ce profil.")
        with self._piper_lock:
            if hasattr(voice, "synthesize_stream_raw"):          # 1.2
                raw = b"".join(voice.synthesize_stream_raw(text))
                return np.frombuffer(raw, dtype=np.int16), voice.config.sample_rate
            chunks = list(voice.synthesize(text))                # 1.3+
            raw = b"".join(c.audio_int16_bytes for c in chunks)
            return np.frombuffer(raw, dtype=np.int16), chunks[0].sample_rate

    def _synth_edge(self, text: str):
        import edge_tts, miniaudio
        voice_name = self.profile["edge"]

        async def fetch():
            comm = edge_tts.Communicate(text, voice_name, rate=self.edge_rate)
            buf = bytearray()
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    buf.extend(chunk["data"])
            return bytes(buf)

        mp3 = asyncio.run(fetch())
        dec = miniaudio.decode(mp3, output_format=miniaudio.SampleFormat.SIGNED16,
                               nchannels=1, sample_rate=24000)
        return np.frombuffer(dec.samples, dtype=np.int16), dec.sample_rate

    def _synth(self, text: str):
        if self.engine == "edge":
            try:
                return self._synth_edge(text)
            except Exception as e:
                if self._piper_voice() is None:
                    raise
                if not self._warned:
                    print(f"[voix en ligne indisponible ({type(e).__name__}) -> repli sur Piper]")
                    self._warned = True
        return self._synth_piper(text)

    # ---- phrases d'attente pré-synthétisées -----------------------------
    def warm(self, phrases):
        """Synthétise les phrases en arrière-plan avec la voix actuelle (échecs ignorés)."""
        voice = self.current

        def job():
            for p in phrases:
                if self.current != voice:   # la voix a changé entre-temps : on s'arrête
                    return
                if (voice, p) in self._phrase_cache:
                    continue
                try:
                    self._phrase_cache[(voice, p)] = self._synth(clean_for_speech(p))
                except Exception:
                    return                  # hors-ligne par exemple : pas de phrase d'attente, tant pis

        threading.Thread(target=job, daemon=True).start()

    def play_cached(self, phrase: str) -> bool:
        item = self._phrase_cache.get((self.current, phrase))
        if item is None:
            return False                    # pas encore prête : mieux vaut le silence qu'un retard
        self.audio.play_array(*item)
        return True

    # ---- lecture -------------------------------------------------------
    def speak(self, text: str) -> float:
        """Lit le texte. Retourne le délai avant le premier son (en secondes)."""
        sentences = split_sentences(clean_for_speech(text))
        if not sentences:
            return 0.0
        if self.max_chars:  # réponse trop longue pour de l'oral : on lit le début et on propose la suite
            kept, total = [], 0
            for s in sentences:
                if kept and total + len(s) > self.max_chars:
                    kept.append("Je peux t'en dire plus si tu veux.")
                    break
                kept.append(s)
                total += len(s)
            sentences = kept
        q = queue.Queue(maxsize=2)
        DONE = object()

        def producer():
            try:
                for s in sentences:
                    q.put(self._synth(s))
            except Exception as e:
                q.put(e)
            q.put(DONE)

        t0 = time.time()
        threading.Thread(target=producer, daemon=True).start()
        first_sound = None
        while True:
            item = q.get()
            if item is DONE:
                break
            if isinstance(item, Exception):
                raise item
            if first_sound is None:
                first_sound = time.time() - t0
            self.audio.play_array(*item)
        return first_sound or 0.0
