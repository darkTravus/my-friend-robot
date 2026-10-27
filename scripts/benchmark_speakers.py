"""Banc local d'évaluation des scores d'empreintes vocales WeSpeaker."""
import argparse
import time
import wave
from pathlib import Path

import numpy as np

from core.speaker import compute_fbank

SAMPLE_RATE = 16000


def load_wav(path):
    with wave.open(str(path), "rb") as audio:
        if audio.getcomptype() != "NONE":
            raise ValueError(f"{path} : WAV compressé non pris en charge.")
        if audio.getnchannels() != 1 or audio.getsampwidth() != 2:
            raise ValueError(f"{path} : attendu un WAV mono PCM 16 bits.")
        if audio.getframerate() != SAMPLE_RATE:
            raise ValueError(f"{path} : attendu {SAMPLE_RATE} Hz, reçu {audio.getframerate()} Hz.")
        frames = audio.readframes(audio.getnframes())
    samples = np.frombuffer(frames, dtype="<i2").astype(np.float32)
    if not samples.size:
        raise ValueError(f"{path} : le fichier audio est vide.")
    return samples, len(samples) / SAMPLE_RATE


def extract_embedding(path, session):
    samples, duration = load_wav(path)
    features = compute_fbank(samples)
    started = time.perf_counter()
    output = session.run(["embs"], {"feats": features[np.newaxis, ...]})[0]
    inference_seconds = time.perf_counter() - started
    embedding = np.asarray(output, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(embedding))
    if not norm:
        raise ValueError(f"Le modèle a produit une empreinte vide pour {path.name}.")
    return embedding / norm, duration, inference_seconds


def make_profile(embeddings):
    if len(embeddings) < 2:
        raise ValueError("Chaque profil doit avoir au moins deux extraits d'enrôlement.")
    profile = np.mean(np.stack(embeddings), axis=0)
    norm = float(np.linalg.norm(profile))
    if not norm:
        raise ValueError("Impossible de calculer le profil vocal à partir des extraits.")
    return profile / norm


def score_test_embeddings(profiles, test_embeddings):
    if len(profiles) < 2:
        raise ValueError("Il faut au moins deux profils vocaux.")
    if any(speaker not in profiles for speaker, _ in test_embeddings):
        raise ValueError("Chaque voix testée doit avoir un profil d'enrôlement correspondant.")

    speakers = sorted(profiles)
    genuine, impostor, predictions = [], [], []
    for true_speaker, embedding in test_embeddings:
        scores = {
            speaker: float(np.dot(embedding, profiles[speaker]))
            for speaker in speakers
        }
        genuine.append(scores[true_speaker])
        impostor.extend(score for speaker, score in scores.items() if speaker != true_speaker)
        predicted_speaker = max(scores, key=scores.get)
        predictions.append((true_speaker, predicted_speaker, scores[predicted_speaker]))
    if not genuine or not impostor:
        raise ValueError("Ajoute au moins un extrait de test pour chaque personne.")
    return genuine, impostor, predictions


def threshold_metrics(genuine, impostor, threshold):
    false_rejects = sum(score < threshold for score in genuine)
    false_accepts = sum(score >= threshold for score in impostor)
    return {
        "false_rejects": false_rejects,
        "genuine_count": len(genuine),
        "false_accepts": false_accepts,
        "impostor_count": len(impostor),
        "false_reject_rate": false_rejects / len(genuine),
        "false_accept_rate": false_accepts / len(impostor),
    }


def identification_metrics(predictions, threshold):
    rejected = sum(score < threshold for _, _, score in predictions)
    false_identifications = sum(
        true_speaker != predicted_speaker and score >= threshold
        for true_speaker, predicted_speaker, score in predictions
    )
    correct_identifications = len(predictions) - rejected - false_identifications
    total = len(predictions)
    return {
        "rejected": rejected,
        "false_identifications": false_identifications,
        "correct_identifications": correct_identifications,
        "total": total,
        "rejection_rate": rejected / total,
        "false_identification_rate": false_identifications / total,
        "correct_identification_rate": correct_identifications / total,
    }


def print_scores(label, values):
    print(
        f"{label}: n={len(values)}, min={min(values):.3f}, "
        f"moyenne={np.mean(values):.3f}, max={max(values):.3f}"
    )


def evaluate(samples_dir, model_path, threshold=None):
    if not model_path.is_file():
        raise FileNotFoundError(f"Modèle ONNX introuvable : {model_path}")
    if not samples_dir.is_dir():
        raise FileNotFoundError(f"Dossier d'échantillons introuvable : {samples_dir}")
    speaker_dirs = sorted(path for path in samples_dir.iterdir() if path.is_dir())
    if len(speaker_dirs) < 2:
        raise ValueError("Crée au moins deux sous-dossiers, un par personne.")

    try:
        import onnxruntime as ort
    except ImportError as exc:
        raise RuntimeError(
            "Dépendance manquante : installe requirements-speaker-benchmark.txt."
        ) from exc

    options = ort.SessionOptions()
    options.inter_op_num_threads = 1
    options.intra_op_num_threads = 1
    session = ort.InferenceSession(str(model_path), sess_options=options)
    input_names = {item.name for item in session.get_inputs()}
    output_names = {item.name for item in session.get_outputs()}
    if "feats" not in input_names or "embs" not in output_names:
        raise ValueError("Le modèle doit exposer les entrées 'feats' et la sortie 'embs'.")

    profiles = {}
    test_embeddings = []
    inference_times = []
    for speaker_dir in speaker_dirs:
        enrollment_dir = speaker_dir / "enrollment"
        test_dir = speaker_dir / "test"
        enrollment_wavs = sorted(enrollment_dir.glob("*.wav")) if enrollment_dir.is_dir() else []
        test_wavs = sorted(test_dir.glob("*.wav")) if test_dir.is_dir() else []
        if len(enrollment_wavs) < 2:
            raise ValueError(f"{speaker_dir.name}/enrollment : ajoute au moins deux WAV.")
        if not test_wavs:
            raise ValueError(f"{speaker_dir.name}/test : ajoute au moins un WAV.")

        enrollment_embeddings = []
        for wav_path in enrollment_wavs:
            embedding, duration, inference_seconds = extract_embedding(wav_path, session)
            enrollment_embeddings.append(embedding)
            inference_times.append(inference_seconds)
            short_notice = " (moins de 3 s)" if duration < 3 else ""
            print(f"{speaker_dir.name}/enrollment/{wav_path.name}: {duration:.1f} s, "
                  f"inférence ONNX {inference_seconds * 1000:.0f} ms{short_notice}")

        profiles[speaker_dir.name] = make_profile(enrollment_embeddings)
        for wav_path in test_wavs:
            embedding, duration, inference_seconds = extract_embedding(wav_path, session)
            test_embeddings.append((speaker_dir.name, embedding))
            inference_times.append(inference_seconds)
            short_notice = " (moins de 3 s)" if duration < 3 else ""
            print(f"{speaker_dir.name}/test/{wav_path.name}: {duration:.1f} s, "
                  f"inférence ONNX {inference_seconds * 1000:.0f} ms{short_notice}")

    genuine, impostor, predictions = score_test_embeddings(profiles, test_embeddings)
    print_scores("Test authentique (score face au bon profil)", genuine)
    print_scores("Test imposteur (scores face aux autres profils)", impostor)
    correct = sum(true == predicted for true, predicted, _ in predictions)
    print(f"Attribution du meilleur profil, sans rejet : {correct}/{len(predictions)} "
          f"({correct / len(predictions):.1%})")
    print(f"Latence ONNX sur ce PC : moyenne {np.mean(inference_times) * 1000:.0f} ms, "
          f"max {max(inference_times) * 1000:.0f} ms (hors extraction des caractéristiques).")

    print("Balayage exploratoire des seuils (acceptation si score >= seuil) :")
    print("  Les FAR/FRR sont calculés par comparaison profil-test ; "
          "l'identification est calculée par extrait de test.")
    for candidate in np.linspace(-1.0, 1.0, 21):
        metrics = threshold_metrics(genuine, impostor, float(candidate))
        id_metrics = identification_metrics(predictions, float(candidate))
        print(f"  {candidate:+.2f}: FRR "
              f"{metrics['false_rejects']}/{metrics['genuine_count']} "
              f"({metrics['false_reject_rate']:.1%}), FAR "
              f"{metrics['false_accepts']}/{metrics['impostor_count']} "
              f"({metrics['false_accept_rate']:.1%}), identifications correctes "
              f"{id_metrics['correct_identifications']}/{id_metrics['total']}, "
              f"fausses identifications {id_metrics['false_identifications']}, "
              f"rejets {id_metrics['rejected']}")

    if threshold is not None:
        metrics = threshold_metrics(genuine, impostor, threshold)
        id_metrics = identification_metrics(predictions, threshold)
        print(f"Seuil exploratoire {threshold:.3f}: faux rejets "
              f"{metrics['false_rejects']}/{metrics['genuine_count']} "
              f"({metrics['false_reject_rate']:.1%}), fausses acceptations "
              f"{metrics['false_accepts']}/{metrics['impostor_count']} "
              f"({metrics['false_accept_rate']:.1%}); identifications correctes "
              f"{id_metrics['correct_identifications']}/{id_metrics['total']}, "
              f"fausses identifications {id_metrics['false_identifications']}, "
              f"rejets {id_metrics['rejected']}")


def main():
    parser = argparse.ArgumentParser(
        description="Évalue localement des profils vocaux sur des extraits distincts."
    )
    parser.add_argument("--samples", type=Path, required=True,
                        help="Dossier contenant speaker-id/enrollment/*.wav et speaker-id/test/*.wav.")
    parser.add_argument("--model", type=Path, required=True, help="Chemin du modèle ONNX WeSpeaker.")
    parser.add_argument("--threshold", type=float,
                        help="Seuil exploratoire de similarité cosinus, en plus du balayage.")
    args = parser.parse_args()
    try:
        evaluate(args.samples, args.model, args.threshold)
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
