"""Robot conversationnel : écoute permanente (mot d'activation), conversation vocale, visage animé.

Console : Entrée = réveiller | v = voix | r = nouvelle conversation | q = quitter
Fenêtre : Espace = réveiller | Échap = quitter"""
import argparse
import os
import queue
import random
import sys
import threading
import time

import yaml
import sounddevice as sd
from dotenv import load_dotenv
from openai import OpenAI

from core import settings
from core.audio import Audio
from core.dialogue import is_noise_transcript, user_wants_to_end
from core.filler import Filler
from core.llm import Brain
from core.stt import STT
from core.tts import TTS
from core.wake import make_detector, wait_for_trigger
from modules import ToolRegistry, actus
from ui.state import UIState

HELP = "Commandes : Entrée = réveiller | v = voix | r = nouvelle conversation | q = quitter"


def load_config(path="config.yaml"):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ----------------------------------------------------------------------------- voix
def apply_voice(tts, brain, filler, name) -> bool:
    """Change la voix ET fait parler le robot au bon genre."""
    if not tts.set_voice(name):
        return False
    brain.set_gender(tts.profile.get("genre"))
    settings.save(voice=name)
    filler.warm()  # prépare les phrases d'attente avec la nouvelle voix
    return True


def voice_command(tts, brain, filler, arg: str):
    names = tts.voice_names()
    if not arg:
        for i, n in enumerate(names, 1):
            print(f"  {i}. {n}{'  <- actuelle' if n == tts.current else ''}")
        print("Pour choisir : v <numéro ou nom>   (exemple : v 3  ou  v homme)")
        return
    if arg.isdigit() and 1 <= int(arg) <= len(names):
        arg = names[int(arg) - 1]
    if not apply_voice(tts, brain, filler, arg):
        print(f"Voix inconnue. Disponibles : {', '.join(names)}")
        return
    print(f"Voix : {arg}")
    tts.speak("Voilà, c'est ma nouvelle voix. Qu'en penses-tu ?")


# ----------------------------------------------------------------------------- console
def console_thread(events, stop):
    """Lit le clavier en parallèle, sans jamais bloquer le robot."""
    while not stop.is_set():
        try:
            line = input().strip().lower()
        except EOFError:
            return
        events.put(("wake", "key") if not line else ("cmd", line))


# ----------------------------------------------------------------------------- boucle du robot
def robot_loop(cfg, audio, stt, brain, tts, filler, detector, events, ui, stop):
    conv = cfg.get("conversation", {})
    first_wait = float(conv.get("first_wait_seconds", 6))
    follow_up = float(conv.get("follow_up_seconds", 6))
    follow_up_q = float(conv.get("follow_up_question_seconds", 10))
    auto_end = bool(conv.get("auto_end", True))
    wake_reply = conv.get("wake_reply", "voice")
    replies = conv.get("wake_replies", [])

    def standby():
        ui.mode = "idle"
        how = "dis le mot d'activation, " if detector else ""
        print(f"\n[En veille] {how}appuie sur Entrée (console) ou Espace (fenêtre).  {HELP}")

    def acknowledge():
        """Après le réveil : le robot répond ("Oui ?") plutôt qu'un bip. Phrases pré-synthétisées = instantané."""
        said = False
        if wake_reply == "voice" and replies:
            ui.show_emotion("curiosite")
            ui.mode = "speaking"
            said = tts.play_cached(random.choice(replies))   # False si la phrase n'est pas encore prête
        if not said and wake_reply != "none":
            audio.beep()                                     # repli : bip
        time.sleep(0.12)                                     # laisse mourir l'écho avant d'écouter
        audio.flush()

    standby()
    while not stop.is_set():
        try:
            ev = wait_for_trigger(audio, detector, events, stop)
            if ev is None or ev[0] == "quit":
                break
            if ev[0] == "cmd":
                cmd = ev[1]
                if cmd in ("q", "quit", "exit"):
                    break
                elif cmd == "r":
                    brain.reset()
                    print("Mémoire effacée.")
                elif cmd == "v" or cmd.startswith("v "):
                    ui.show_emotion("joie")
                    ui.mode = "speaking"
                    voice_command(tts, brain, filler, cmd[1:].strip())
                else:
                    print(HELP)
                ui.mode = "idle"
                continue

            # ---- réveil : une conversation commence
            print("[Réveillé]" + (" (mot d'activation)" if ev[1] == "word" else ""))
            audio.flush()
            acknowledge()

            wait_s = first_wait
            while not stop.is_set():
                ui.mode = "listening"
                wav = audio.record_until_silence(wait_s)
                if wav is None:
                    break          # personne ne parle : retour en veille

                ui.mode = "thinking"
                t0 = time.time()
                text = stt.transcribe(wav, brain.last_answer())
                t1 = time.time()
                if not text or is_noise_transcript(text):
                    break          # bruit / télé : on n'invente pas une conversation
                print(f"Toi    : {text}")

                filler.start_turn()
                answer = brain.reply(text)
                t2 = time.time()
                print(f"Robot  : {answer}   [{brain.emotion}{'+fin' if brain.wants_end else ''}]")

                filler.wait()      # laisse finir la phrase d'attente avant de répondre
                ui.show_emotion(brain.emotion)
                ui.mode = "speaking"
                first_sound = tts.speak(answer)
                print(f"[STT {t1 - t0:.1f}s | LLM+outils {t2 - t1:.1f}s | 1er son après {first_sound:.1f}s | "
                      f"lecture complète {time.time() - t2:.1f}s]")

                time.sleep(0.3)    # laisse mourir l'écho du haut-parleur, puis on jette ce que le micro a capté
                audio.flush()

                asks = answer.rstrip().endswith("?")
                ended = auto_end and (user_wants_to_end(text) or
                                      (brain.wants_end and not asks and len(text.split()) <= 8))
                if ended:
                    print("[Conversation terminée : retour en veille]")
                    ui.show_emotion("joie" if brain.emotion == "neutre" else brain.emotion, hold=2.5)
                    break
                wait_s = follow_up_q if asks else follow_up   # question posée : on laisse plus de temps
            standby()
        except Exception as e:  # on ne plante pas sur une erreur réseau ponctuelle
            print(f"Erreur : {e}")
            standby()
    stop.set()


# ----------------------------------------------------------------------------- programme
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--devices", action="store_true", help="liste les micros/haut-parleurs")
    ap.add_argument("--noise", action="store_true", help="mesure le bruit ambiant (réglage du seuil)")
    ap.add_argument("--tools", action="store_true", help="teste la météo, les flux RSS et la recherche web")
    ap.add_argument("--wake-test", action="store_true", help="affiche le score du mot d'activation en direct")
    ap.add_argument("--no-ui", action="store_true", help="sans fenêtre (mode console seulement)")
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
    if args.wake_test:
        det = make_detector(cfg.get("wake", {}))
        if det is None:
            sys.exit("Aucun détecteur actif : vérifie wake.mode et l'installation (requirements-wake.txt).")
        audio.start()
        print("Dis ton mot d'activation (Ctrl+C pour arrêter). Un score s'affiche dès qu'il dépasse 0.05.")
        try:
            while True:
                if det.process(audio.read_block()) or det.last_score > 0.05:
                    print(f"  score {det.last_score:.2f} {'#' * int(det.last_score * 40)}")
        except KeyboardInterrupt:
            return
    if args.tools:
        reg = ToolRegistry(cfg)
        print("Outils chargés :", ", ".join(reg.names()))
        print("\n--- Météo ---\n" + reg.call("get_weather", "{}"))
        print("\n--- Actualités (une) ---\n" + reg.call("get_news", '{"category": "une"}'))
        print("\n--- Recherche web ---\n" + reg.call("search_web", '{"query": "sorties animés saison automne", "recent": false}'))
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
    ui = UIState()
    conv = cfg.get("conversation", {})
    extra = conv.get("wake_replies", []) if conv.get("wake_reply", "voice") == "voice" else []
    filler = Filler(tts, registry, cfg.get("fillers"), ui=ui, extra_phrases=extra)
    brain.on_slow_tool, brain.tool_delay = filler.on_slow, filler.delay
    brain.tool_timeout = float(cfg.get("tools", {}).get("timeout_seconds", 12))
    filler.warm()  # synthèse en arrière-plan des phrases d'attente
    detector = make_detector(cfg.get("wake", {}))

    audio.start()  # le micro écoute désormais en permanence
    print(f"Robot prêt. Voix actuelle : {tts.current}")

    events, stop = queue.Queue(), threading.Event()
    worker = threading.Thread(target=robot_loop, daemon=True,
                              args=(cfg, audio, stt, brain, tts, filler, detector, events, ui, stop))
    worker.start()
    threading.Thread(target=console_thread, args=(events, stop), daemon=True).start()

    uicfg = cfg.get("ui", {})
    try:
        if uicfg.get("enabled", True) and not args.no_ui:
            try:
                from ui.window import run_window
                run_window(ui, audio, events, stop, scale=int(uicfg.get("scale", 2)),
                           fps=int(uicfg.get("fps", 30)), gain=float(uicfg.get("bar_gain", 1.0)),
                           sleep_after=float(uicfg.get("sleep_after_seconds", 90)))
            except ImportError as e:
                print(f"[fenêtre indisponible ({e}) : mode console. Linux : sudo apt install python3-tk]")
        while not stop.is_set():
            time.sleep(0.2)
    except KeyboardInterrupt:
        pass
    stop.set()
    worker.join(timeout=3)
    audio.stop()
    print("À bientôt !")


if __name__ == "__main__":
    main()
