"""Phase 1 : prototype vocal sur PC.  Entrée -> tu parles -> le robot répond."""
import argparse
import os
import sys
import time
import yaml
import sounddevice as sd
from dotenv import load_dotenv
from openai import OpenAI

from core import settings
from core.audio import Audio
from core.stt import STT
from core.llm import Brain
from core.tts import TTS
from core.filler import Filler
from modules import ToolRegistry, actus


def load_config(path="config.yaml"):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def apply_voice(tts, brain, filler, name) -> bool:
    """Change la voix ET fait parler le robot au bon genre."""
    if not tts.set_voice(name):
        return False
    brain.set_gender(tts.profile.get("genre"))
    settings.save(voice=name)
    filler.warm()  # prépare les phrases d'attente avec la nouvelle voix
    return True


def voice_menu(tts, brain, filler, arg: str):
    names = tts.voice_names()
    if not arg:
        for i, n in enumerate(names, 1):
            mark = "  <- actuelle" if n == tts.current else ""
            print(f"  {i}. {n}{mark}")
        arg = input("Numéro ou nom de la voix : ").strip().lower()
    if arg.isdigit() and 1 <= int(arg) <= len(names):
        arg = names[int(arg) - 1]
    if not apply_voice(tts, brain, filler, arg):
        print(f"Voix inconnue. Disponibles : {', '.join(names)}")
        return
    print(f"Voix : {arg}")
    tts.speak("Voilà, c'est ma nouvelle voix. Qu'en penses-tu ?")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--devices", action="store_true", help="liste les micros/haut-parleurs")
    ap.add_argument("--noise", action="store_true", help="mesure le bruit ambiant (réglage du seuil)")
    ap.add_argument("--tools", action="store_true", help="teste la météo et les flux RSS (sans voix ni LLM)")
    args = ap.parse_args()

    load_dotenv()
    cfg = load_config()
    audio = Audio(cfg["audio"])
    if cfg["llm"].get("debug_timing"):  # affiche "Retrying request..." : révèle les limites de débit de l'API
        import logging
        logging.basicConfig(format="  [%(name)s] %(message)s")
        logging.getLogger("openai").setLevel(logging.INFO)

    if args.devices:
        print(sd.query_devices())
        return
    if args.noise:
        print("Reste silencieux 2 secondes...")
        print(f"Niveau de bruit : {audio.measure_noise():.4f}")
        print("Règle audio.silence_threshold à environ 2 à 3 fois cette valeur.")
        return

    if args.tools:
        reg = ToolRegistry(cfg)
        print("Outils chargés :", ", ".join(reg.names()))
        print("\n--- Météo ---\n" + reg.call("get_weather", "{}"))
        print("\n--- Actualités (une) ---\n" + reg.call("get_news", '{"category": "une"}'))
        print("\n--- Recherche web ---\n" + reg.call("search_web", '{"query": "prochains animés de la saison", "recent": true}'))
        print("\n--- État des flux RSS ---")
        actus.check_feeds(cfg)
        return

    key = os.getenv(cfg["api"]["api_key_env"])
    if not key:
        sys.exit("Clé d'API manquante : crée le fichier .env (voir .env.example).")

    # la voix choisie la dernière fois (settings.json) remplace celle de config.yaml
    cfg["tts"]["voice"] = settings.load().get("voice", cfg["tts"].get("voice"))

    client = OpenAI(base_url=cfg["api"]["base_url"], api_key=key)
    stt = STT(client, cfg["api"]["stt_model"], cfg["language"], cfg["api"].get("stt_prompt"))
    registry = ToolRegistry(cfg)
    brain = Brain(client, cfg["llm"], cfg["api"]["llm_model"], tools=registry)
    tts = TTS(cfg["tts"], audio)
    brain.set_gender(tts.profile.get("genre"))
    filler = Filler(tts, registry, cfg.get("fillers"))
    brain.on_slow_tool, brain.tool_delay = filler.on_slow, filler.delay
    brain.tool_timeout = float(cfg.get("tools", {}).get("timeout_seconds", 12))
    filler.warm()  # synthèse en arrière-plan des phrases d'attente

    print("Robot prêt.  Entrée = parler | v = changer de voix | r = nouvelle conversation | Ctrl+C = quitter")
    print(f"Voix actuelle : {tts.current}")
    while True:
        try:
            cmd = input("\n[Entrée pour parler] ").strip().lower()
            if cmd == "r":
                brain.reset()
                print("Mémoire effacée.")
                continue
            if cmd == "v" or cmd.startswith("v "):
                voice_menu(tts, brain, filler, cmd[1:].strip())
                continue

            if cmd:
                print("Commande inconnue. Entrée = parler | v = voix | r = nouvelle conversation")
                continue

            print("Écoute...")
            wav = audio.record_until_silence()
            if wav is None:
                print("(rien entendu)")
                continue

            t0 = time.time()
            text = stt.transcribe(wav, brain.last_answer())
            t1 = time.time()
            if not text:
                print("(transcription vide)")
                continue
            print(f"Toi    : {text}")

            filler.start_turn()
            answer = brain.reply(text)
            t2 = time.time()
            print(f"Robot  : {answer}")

            filler.wait()  # laisse finir la phrase d'attente avant de répondre
            first_sound = tts.speak(answer)
            print(f"[STT {t1 - t0:.1f}s | LLM+outils {t2 - t1:.1f}s | 1er son après {first_sound:.1f}s | "
                  f"lecture complète {time.time() - t2:.1f}s]")
        except KeyboardInterrupt:
            print("\nÀ bientôt !")
            break
        except Exception as e:  # on ne plante pas sur une erreur réseau ponctuelle
            print(f"Erreur : {e}")


if __name__ == "__main__":
    main()
