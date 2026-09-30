"""Phase 1 : prototype vocal sur PC.  Entrée -> tu parles -> le robot répond."""
import argparse
import os
import sys
import time
import yaml
import sounddevice as sd
from dotenv import load_dotenv
from openai import OpenAI

from core.audio import Audio
from core.stt import STT
from core.llm import Brain
from core.tts import TTS


def load_config(path="config.yaml"):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--devices", action="store_true", help="liste les micros/haut-parleurs")
    ap.add_argument("--noise", action="store_true", help="mesure le bruit ambiant (réglage du seuil)")
    args = ap.parse_args()

    load_dotenv()
    cfg = load_config()
    audio = Audio(cfg["audio"])

    if args.devices:
        print(sd.query_devices())
        return
    if args.noise:
        print("Reste silencieux 2 secondes...")
        print(f"Niveau de bruit : {audio.measure_noise():.4f}")
        print("Règle audio.silence_threshold à environ 2 à 3 fois cette valeur.")
        return

    key = os.getenv(cfg["api"]["api_key_env"])
    if not key:
        sys.exit("Clé d'API manquante : crée le fichier .env (voir .env.example).")

    client = OpenAI(base_url=cfg["api"]["base_url"], api_key=key)
    stt = STT(client, cfg["api"]["stt_model"], cfg["language"])
    brain = Brain(client, cfg["llm"], cfg["api"]["llm_model"])
    tts = TTS(cfg["tts"]["piper_model"], audio)

    print("Robot prêt. Entrée = parler | 'r' + Entrée = nouvelle conversation | Ctrl+C = quitter")
    while True:
        try:
            cmd = input("\n[Entrée pour parler] ").strip().lower()
            if cmd == "r":
                brain.reset()
                print("Mémoire effacée.")
                continue

            print("Écoute...")
            wav = audio.record_until_silence()
            if wav is None:
                print("(rien entendu)")
                continue

            t0 = time.time()
            text = stt.transcribe(wav)
            t1 = time.time()
            if not text:
                print("(transcription vide)")
                continue
            print(f"Toi    : {text}")

            answer = brain.reply(text)
            t2 = time.time()
            print(f"Robot  : {answer}")

            tts.speak(answer)
            print(f"[STT {t1 - t0:.1f}s | LLM {t2 - t1:.1f}s | TTS+lecture {time.time() - t2:.1f}s]")
        except KeyboardInterrupt:
            print("\nÀ bientôt !")
            break
        except Exception as e:  # on ne plante pas sur une erreur réseau ponctuelle
            print(f"Erreur : {e}")


if __name__ == "__main__":
    main()
