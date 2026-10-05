"""Enregistrement micro (avec détection de fin de phrase) et lecture audio."""
import io
from collections import deque
import wave
import numpy as np
import sounddevice as sd


class Audio:
    def __init__(self, cfg: dict):
        self.sr = cfg["sample_rate"]
        self.threshold = cfg["silence_threshold"]
        self.silence_duration = cfg["silence_duration"]
        self.max_seconds = cfg["max_record_seconds"]
        self.in_dev = cfg.get("input_device")
        self.out_dev = cfg.get("output_device")

    def record_until_silence(self):
        """Écoute jusqu'à la fin d'une phrase. Retourne un WAV (bytes) ou None si rien n'a été dit."""
        block = int(self.sr * 0.05)  # blocs de 50 ms
        frames, speech_started, silent_blocks = [], False, 0
        preroll = deque(maxlen=int(0.5 / 0.05))  # on garde 0,5 s avant la détection : évite de couper le début
        max_blocks = int(self.max_seconds / 0.05)
        silence_blocks_needed = int(self.silence_duration / 0.05)
        waiting_blocks_max = int(6 / 0.05)  # abandon si personne ne parle pendant 6 s

        with sd.InputStream(samplerate=self.sr, channels=1, dtype="float32",
                            blocksize=block, device=self.in_dev) as stream:
            for i in range(max_blocks):
                data, _ = stream.read(block)
                level = float(np.sqrt(np.mean(data ** 2)))  # volume (RMS)
                if not speech_started:
                    if level > self.threshold:
                        speech_started, silent_blocks = True, 0
                        frames.extend(preroll)
                        frames.append(data.copy())
                    else:
                        preroll.append(data.copy())
                        if i > waiting_blocks_max:
                            return None
                else:
                    frames.append(data.copy())
                    if level > self.threshold:
                        silent_blocks = 0
                    else:
                        silent_blocks += 1
                        if silent_blocks >= silence_blocks_needed:
                            break
        if not frames:
            return None
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

    def play_wav(self, wav_path: str):
        with wave.open(wav_path, "rb") as w:
            sr, ch = w.getframerate(), w.getnchannels()
            data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
        if ch > 1:
            data = data.reshape(-1, ch)
        sd.play(data, sr, device=self.out_dev)
        sd.wait()

    def play_array(self, data, sr):
        """Lit un tableau int16 mono."""
        sd.play(data, sr, device=self.out_dev)
        sd.wait()

    def measure_noise(self, seconds: float = 2.0) -> float:
        """Utilitaire pour régler silence_threshold."""
        rec = sd.rec(int(self.sr * seconds), samplerate=self.sr, channels=1,
                     dtype="float32", device=self.in_dev)
        sd.wait()
        return float(np.sqrt(np.mean(rec ** 2)))
