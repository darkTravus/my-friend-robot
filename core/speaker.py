"""Identification vocale locale et profils explicitement enrôlés."""
import io
import json
import math
import re
import tempfile
import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000


def compute_fbank(samples):
    try:
        import kaldi_native_fbank as knf
    except ImportError as exc:
        raise RuntimeError(
            "Dépendance manquante : installe requirements-speaker-benchmark.txt."
        ) from exc

    options = knf.FbankOptions()
    options.frame_opts.samp_freq = SAMPLE_RATE
    options.frame_opts.frame_length_ms = 25
    options.frame_opts.frame_shift_ms = 10
    options.frame_opts.dither = 0
    options.frame_opts.window_type = "hamming"
    options.frame_opts.snip_edges = True
    options.mel_opts.num_bins = 80
    options.mel_opts.debug_mel = False
    fbank = knf.OnlineFbank(options)
    fbank.accept_waveform(SAMPLE_RATE, samples.tolist())
    fbank.input_finished()
    features = np.asarray(
        [fbank.get_frame(i) for i in range(fbank.num_frames_ready)],
        dtype=np.float32,
    )
    if features.size == 0:
        raise ValueError("Audio trop court pour calculer les caractéristiques vocales.")
    features -= np.mean(features, axis=0, keepdims=True)
    return features


def _normalized_embedding(embedding):
    vector = np.asarray(embedding, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(vector))
    if not vector.size or not math.isfinite(norm) or norm == 0:
        raise ValueError("Empreinte vocale vide ou invalide.")
    return vector / norm


class SpeakerProfileStore:
    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        if not self.path.exists():
            return {}
        with self.path.open(encoding="utf-8") as source:
            data = json.load(source)
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ValueError("Le fichier des profils vocaux a un format invalide.")
        profiles = data.get("profiles")
        if not isinstance(profiles, dict):
            raise ValueError("Le fichier des profils vocaux a un format invalide.")

        validated = {}
        for profile_id, profile in profiles.items():
            if not self.is_valid_id(profile_id) or not isinstance(profile, dict):
                raise ValueError("Le fichier des profils vocaux a un format invalide.")
            name = profile.get("display_name")
            interests = profile.get("interests")
            embedding = profile.get("embedding")
            if (not isinstance(name, str) or not name.strip()
                    or not isinstance(interests, list)
                    or any(not isinstance(item, str) or not item.strip() for item in interests)
                    or not isinstance(embedding, list)
                    or not embedding
                    or any(not isinstance(item, (int, float)) or not math.isfinite(item)
                           for item in embedding)):
                raise ValueError(f"Le profil {profile_id} a un format invalide.")
            validated[profile_id] = {
                "display_name": name.strip(),
                "interests": [item.strip() for item in interests],
                "embedding": _normalized_embedding(embedding).tolist(),
            }
        embedding_sizes = {len(profile["embedding"]) for profile in validated.values()}
        if len(embedding_sizes) > 1:
            raise ValueError("Les profils vocaux n'ont pas tous la même dimension.")
        return validated

    def save(self, profiles):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent, delete=False) as target:
            json.dump({"version": 1, "profiles": profiles}, target, ensure_ascii=False, indent=2)
            target.write("\n")
            temporary = Path(target.name)
        try:
            temporary.replace(self.path)
        except OSError:
            temporary.unlink(missing_ok=True)
            raise

    @staticmethod
    def is_valid_id(profile_id):
        return isinstance(profile_id, str) and re.fullmatch(
            r"[a-z0-9][a-z0-9_-]{0,47}", profile_id
        ) is not None

    def add(self, profile_id, display_name, interests, embedding):
        if not self.is_valid_id(profile_id):
            raise ValueError("L'identifiant doit contenir 1 à 48 caractères minuscules, chiffres, _ ou -.")
        display_name = display_name.strip() if isinstance(display_name, str) else ""
        if not display_name:
            raise ValueError("Le nom d'usage ne peut pas être vide.")
        if not isinstance(interests, list) or any(
                not isinstance(item, str) or not item.strip() for item in interests):
            raise ValueError("Les centres d'intérêt doivent être des textes non vides.")
        profiles = self.load()
        if profile_id in profiles:
            raise ValueError(f"Le profil {profile_id} existe déjà.")
        profiles[profile_id] = {
            "display_name": display_name,
            "interests": list(dict.fromkeys(item.strip() for item in interests)),
            "embedding": _normalized_embedding(embedding).tolist(),
        }
        self.save(profiles)

    def remove(self, profile_id):
        profiles = self.load()
        if profile_id not in profiles:
            return False
        del profiles[profile_id]
        self.save(profiles)
        return True


class SpeakerIdentifier:
    def __init__(self, model_path, profiles_path, threshold=0.30,
                 ambiguity_margin=0.05, minimum_duration=3.0, session=None):
        self.store = SpeakerProfileStore(profiles_path)
        self.threshold = float(threshold)
        self.ambiguity_margin = float(ambiguity_margin)
        self.minimum_duration = float(minimum_duration)
        if not -1 <= self.threshold <= 1:
            raise ValueError("Le seuil d'identification doit être compris entre -1 et 1.")
        if not 0 <= self.ambiguity_margin <= 2:
            raise ValueError("La marge d'ambiguïté doit être comprise entre 0 et 2.")
        if self.minimum_duration <= 0:
            raise ValueError("La durée minimale doit être supérieure à zéro.")
        if session is None:
            try:
                import onnxruntime as ort
            except ImportError as exc:
                raise RuntimeError(
                    "Dépendance manquante : installe requirements-speaker-benchmark.txt."
                ) from exc
            model_path = Path(model_path)
            if not model_path.is_file():
                raise FileNotFoundError(f"Modèle ONNX introuvable : {model_path}")
            options = ort.SessionOptions()
            options.inter_op_num_threads = 1
            options.intra_op_num_threads = 1
            session = ort.InferenceSession(str(model_path), sess_options=options)
        self.session = session
        input_names = {item.name for item in session.get_inputs()}
        output_names = {item.name for item in session.get_outputs()}
        if "feats" not in input_names or "embs" not in output_names:
            raise ValueError("Le modèle doit exposer les entrées 'feats' et la sortie 'embs'.")
        self.profiles = self.store.load()
        self.embedding_size = next(
            (len(profile["embedding"]) for profile in self.profiles.values()), None
        )

    @staticmethod
    def audio_samples(wav_bytes):
        with wave.open(io.BytesIO(wav_bytes), "rb") as audio:
            if (audio.getcomptype() != "NONE" or audio.getnchannels() != 1
                    or audio.getsampwidth() != 2 or audio.getframerate() != SAMPLE_RATE):
                raise ValueError("La voix doit être un WAV mono PCM 16 bits à 16 kHz.")
            samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2")
        if not samples.size:
            raise ValueError("L'enregistrement vocal est vide.")
        return samples.astype(np.float32), len(samples) / SAMPLE_RATE

    def embedding_from_samples(self, samples):
        features = compute_fbank(samples)
        output = self.session.run(
            ["embs"], {"feats": features[np.newaxis, ...]}
        )[0]
        embedding = _normalized_embedding(output)
        if self.embedding_size is not None and len(embedding) != self.embedding_size:
            raise ValueError("La dimension de l'empreinte ne correspond pas aux profils enrôlés.")
        return embedding

    def enroll(self, profile_id, display_name, interests, recordings):
        if len(recordings) < 3:
            raise ValueError("Enregistre au moins trois phrases distinctes.")
        embeddings = []
        for recording in recordings:
            samples, duration = self.audio_samples(recording)
            if duration < self.minimum_duration:
                raise ValueError(
                    f"Un enregistrement dure {duration:.1f} s ; "
                    f"minimum requis : {self.minimum_duration:.1f} s."
                )
            embeddings.append(self.embedding_from_samples(samples))
        profile_embedding = _normalized_embedding(np.mean(np.stack(embeddings), axis=0))
        self.store.add(profile_id, display_name, interests, profile_embedding)
        self.profiles = self.store.load()
        self.embedding_size = len(profile_embedding)

    def identify(self, wav_bytes):
        samples, duration = self.audio_samples(wav_bytes)
        if duration < self.minimum_duration:
            return None, "phrase trop courte", None
        if len(self.profiles) < 2:
            return None, "au moins deux profils requis", None
        embedding = self.embedding_from_samples(samples)
        scores = []
        for profile_id, profile in self.profiles.items():
            vector = _normalized_embedding(profile["embedding"])
            if len(vector) != len(embedding):
                raise ValueError("Les profils vocaux n'ont pas tous la même dimension.")
            scores.append((float(np.dot(embedding, vector)), profile_id, profile))
        scores.sort(reverse=True, key=lambda item: item[0])
        best_score, profile_id, profile = scores[0]
        if best_score < self.threshold:
            return None, "score sous le seuil", best_score
        if len(scores) > 1 and best_score - scores[1][0] < self.ambiguity_margin:
            return None, "profils trop proches", best_score
        return {
            "profile_id": profile_id,
            "display_name": profile["display_name"],
            "interests": profile["interests"],
        }, "identifié", best_score
