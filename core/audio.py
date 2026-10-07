"""Audio : micro en écoute permanente (flux continu), enregistrement d'une phrase, lecture,
et niveaux sonores en direct pour les animations du visage."""
import io
import queue
import time
import wave
from collections import deque

import numpy as np
import sounddevice as sd

BLOCK_S = 0.08                       # blocs de 80 ms = 1280 échantillons à 16 kHz (taille attendue par openWakeWord)
BANDS_HZ = [(80, 400), (400, 1500), (1500, 4000)]   # graves, médiums, aigus -> les 3 barres
BAND_BOOST_DB = (0, 6, 12)           # la voix a peu d'aigus : on compense pour équilibrer les barres


class Audio:
    def __init__(self, cfg: dict):
        self.sr = cfg["sample_rate"]
        self.threshold = cfg["silence_threshold"]
        self.silence_duration = cfg["silence_duration"]
        self.max_seconds = cfg["max_record_seconds"]
        self.in_dev = cfg.get("input_device")
        self.out_dev = cfg.get("output_device")
        self.block = int(self.sr * BLOCK_S)
        self._q = queue.Queue(maxsize=250)       # ~20 s de retard maximum, puis les plus récents sont perdus
        self._stream = None
        self.last_block = np.zeros(self.block, dtype=np.float32)
        self.level = 0.0                          # volume du micro (RMS), mis à jour en continu
        self._out = None                          # enveloppe du son en cours de lecture (animation des yeux)

    # ------------------------------------------------------------ micro
    def start(self):
        """Ouvre le micro une fois pour toutes : il écoute en continu, sans bouton."""
        if self._stream is None:
            self._stream = sd.InputStream(samplerate=self.sr, channels=1, dtype="float32",
                                          blocksize=self.block, device=self.in_dev,
                                          callback=self._on_audio)
            self._stream.start()

    def stop(self):
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def _on_audio(self, indata, frames, time_info, status):
        data = indata[:, 0].copy()
        self.last_block = data
        self.level = float(np.sqrt(np.mean(data ** 2)))
        try:
            self._q.put_nowait(data)
        except queue.Full:
            pass

    def read_block(self, timeout: float = 1.0):
        return self._q.get(timeout=timeout)       # lève queue.Empty si le micro ne répond plus

    def flush(self):
        """Jette l'audio en attente (écho du haut-parleur, fin du mot d'activation...)."""
        while True:
            try:
                self._q.get_nowait()
            except queue.Empty:
                return

    # ------------------------------------------------------------ enregistrement d'une phrase
    def record_until_silence(self, max_wait: float = 6.0):
        """Attend que l'utilisateur parle (max_wait secondes), l'enregistre jusqu'à la fin de sa phrase.
        Retourne un WAV (bytes), ou None si personne n'a parlé."""
        frames, speech, silent, spoken = [], False, 0, 0
        preroll = deque(maxlen=int(0.5 / BLOCK_S))   # 0,5 s avant la détection : le début n'est pas coupé
        waited = 0
        need_silence = int(self.silence_duration / BLOCK_S)
        max_blocks = int(self.max_seconds / BLOCK_S)
        max_wait_blocks = int(max_wait / BLOCK_S)
        while True:
            try:
                data = self.read_block(timeout=1.0)
            except queue.Empty:
                return None
            loud = float(np.sqrt(np.mean(data ** 2))) > self.threshold
            if not speech:
                if loud:
                    speech, silent = True, 0
                    frames.extend(preroll)
                    frames.append(data)
                else:
                    preroll.append(data)
                    waited += 1
                    if waited > max_wait_blocks:
                        return None
            else:
                frames.append(data)
                spoken += 1
                silent = 0 if loud else silent + 1
                if silent >= need_silence or spoken >= max_blocks:
                    break
        return self._to_wav(np.concatenate(frames))

    def _to_wav(self, audio):
        pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.sr)
            w.writeframes(pcm.tobytes())
        return buf.getvalue()

    # ------------------------------------------------------------ niveaux pour l'animation
    def band_levels(self):
        """3 valeurs entre 0 et 1 (graves, médiums, aigus) calculées par FFT sur le dernier bloc du micro."""
        x = self.last_block
        if x.size == 0 or not np.any(x):
            return [0.0, 0.0, 0.0]
        rms = float(np.sqrt(np.mean(x ** 2)))
        # porte de bruit : sous ~1/3 du seuil de parole les barres restent au repos (bruit de fond ignoré)
        gate = float(np.clip((rms - 0.35 * self.threshold) / (0.5 * self.threshold), 0.0, 1.0))
        if gate == 0.0:
            return [0.0, 0.0, 0.0]
        mag = np.abs(np.fft.rfft(x * np.hanning(len(x)))) / len(x)
        freqs = np.fft.rfftfreq(len(x), 1.0 / self.sr)
        out = []
        for (lo, hi), boost in zip(BANDS_HZ, BAND_BOOST_DB):
            sel = (freqs >= lo) & (freqs < hi)
            amp = float(np.sqrt(np.sum(mag[sel] ** 2))) + 1e-9
            db = 20 * np.log10(amp) + boost
            out.append(float(np.clip((db + 75) / 40, 0.0, 1.0)) * gate)
        return out

    def out_level(self) -> float:
        """Volume (0 à 1) du son en cours de lecture, à l'instant présent : fait bouger les yeux."""
        o = self._out
        if o is None:
            return 0.0
        env, t0, win = o
        i = int((time.time() - t0) / win)
        return float(min(1.0, env[i] * 6)) if 0 <= i < len(env) else 0.0

    # ------------------------------------------------------------ lecture
    def play_array(self, data, sr):
        """Lit un tableau int16 mono (et calcule son enveloppe pour l'animation)."""
        win = 0.04
        n = int(sr * win)
        count = len(data) // n if n else 0
        if count:
            chunk = data[:count * n].astype(np.float32) / 32768.0
            env = np.sqrt(np.mean(chunk.reshape(count, n) ** 2, axis=1))
        else:
            env = np.zeros(1, dtype=np.float32)
        self._out = (env, time.time(), win)
        try:
            sd.play(data, sr, device=self.out_dev)
            sd.wait()
        finally:
            self._out = None

    def play_wav(self, wav_path: str):
        with wave.open(wav_path, "rb") as w:
            sr, ch = w.getframerate(), w.getnchannels()
            data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        if ch > 1:
            data = data.reshape(-1, ch)
        self.play_array(data, sr)

    def beep(self, freq: float = 880.0, ms: int = 110, volume: float = 0.25):
        """Petit son : 'je t'écoute'."""
        n = int(self.sr * ms / 1000)
        t = np.arange(n) / self.sr
        fade = np.minimum(1.0, np.minimum(t, t[::-1]) / 0.015)      # évite le "clic" au début et à la fin
        tone = (np.sin(2 * np.pi * freq * t) * fade * volume * 32767).astype(np.int16)
        self.play_array(tone, self.sr)

    def measure_noise(self, seconds: float = 2.0) -> float:
        """Utilitaire pour régler silence_threshold."""
        rec = sd.rec(int(self.sr * seconds), samplerate=self.sr, channels=1,
                     dtype="float32", device=self.in_dev)
        sd.wait()
        return float(np.sqrt(np.mean(rec ** 2)))
