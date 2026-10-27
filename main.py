"""Robot conversationnel : écoute permanente (mot d'activation), conversation vocale, visage animé.

Console : Entrée = réveiller | v = voix | r = nouvelle conversation | q = quitter
Fenêtre : Espace = réveiller | Échap = quitter"""
import argparse
from collections import deque
import os
import queue
import random
import sys
import threading
import time
import unicodedata
from pathlib import Path

import yaml
import sounddevice as sd
from dotenv import load_dotenv
from openai import OpenAI

from core import settings
from core.audio import Audio
from core.dialogue import is_noise_transcript, user_wants_to_end
from core.filler import Filler
from core.llm import Brain
from core.speaker import SpeakerIdentifier, SpeakerProfileStore
from core.stt import STT
from core.tts import TTS, join_audio_segments, save_wav
from core.wake import make_detector, wait_for_trigger
from modules import ToolRegistry, actus
from ui.state import UIState

HELP = "Commandes : Entrée = réveiller | v = voix | r = nouvelle conversation | q = quitter"
TTS_TEST_CASES = [
    ("conversation", "Alors, je vois ce que tu veux dire. On peut prendre le temps d'y réfléchir ensemble."),
    ("hesitation", "Euh... je ne suis pas tout à fait sûr. Laisse-moi le formuler autrement : je crois que c'est surtout une question de rythme."),
    ("question", "Tu préfères une réponse courte, ou tu veux que je t'explique un peu plus en détail ?"),
    ("emotion", "Oh, je suis vraiment désolé que ta journée ait été aussi difficile. Tu veux m'en parler un peu ?"),
    ("enchainement", "Il y a deux possibilités. La première est plus simple à mettre en place, tandis que la seconde offre davantage de souplesse. À mon avis, on peut commencer par la première."),
]
ENROLLMENT_PHRASES = [
    "Bonjour, je prends le temps de faire cet enregistrement pour que Zéphyr puisse reconnaître ma voix.",
    "Quand j'ai un moment libre, j'aime parler de mes passions et raconter ce que j'ai découvert récemment.",
    "Aujourd'hui, je vais discuter naturellement, avec mon rythme habituel et ma façon de prononcer les mots.",
    "Je peux parler de musique, de films ou de projets, comme dans une conversation ordinaire.",
    "Même si je suis parfois enthousiaste ou hésitant, ma voix reste bien la mienne.",
]


def load_config(path="config.yaml"):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def enroll_speaker(audio, identifier, speaker_cfg):
    profile_id = input("Identifiant du profil (minuscules, chiffres, tirets) : ").strip()
    display_name = input("Nom d'usage : ").strip()
    interests = [item.strip() for item in input(
        "Centres d'intérêt séparés par des virgules (facultatif) : "
    ).split(",") if item.strip()]
    if not identifier.store.is_valid_id(profile_id):
        raise ValueError("Identifiant invalide : utilise des minuscules, chiffres, tirets ou tirets bas.")
    if not display_name:
        raise ValueError("Le nom d'usage ne peut pas être vide.")
    if profile_id in identifier.store.load():
        raise ValueError(f"Le profil {profile_id} existe déjà.")

    minimum_duration = float(speaker_cfg.get("minimum_duration_seconds", 3.0))
    recordings = []
    for index, phrase in enumerate(ENROLLMENT_PHRASES, 1):
        while True:
            input(f"\nPhrase {index}/{len(ENROLLMENT_PHRASES)} — lis : « {phrase} »\nAppuie sur Entrée quand tu es prêt.")
            audio.flush()
            recording = audio.record_until_silence(max_wait=30)
            if recording is None:
                raise RuntimeError("Aucune voix détectée pendant l'enrôlement.")
            _, duration = identifier.audio_samples(recording)
            if duration < minimum_duration:
                print(f"Enregistrement trop court ({duration:.1f} s). Recommence cette phrase.")
                continue
            recordings.append(recording)
            break
    identifier.enroll(profile_id, display_name, interests, recordings)
    print(
        f"Profil {display_name} enregistré localement. "
        "Les fichiers audio bruts n'ont pas été conservés."
    )


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
def robot_loop(cfg, audio, stt, brain, tts, filler, detector, events, ui, stop,
               speaker_identifier=None):
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
            if ev[1] == "word" and detector:
                print(f"[Réveillé] (mot d'activation, score {detector.last_score:.2f}, "
                      f"seuil {detector.threshold:.2f})")
            else:
                print("[Réveillé]" + (" (mot d'activation)" if ev[1] == "word" else ""))
            if speaker_identifier:
                brain.reset()
                print("[Contexte conversationnel isolé pour cette activation]")
            audio.flush()
            acknowledge()

            recent = deque(maxlen=3)     # dernières émotions : évite un sourire après une triste nouvelle
            wait_s = first_wait
            while not stop.is_set():
                ui.mode = "listening"
                wav = audio.record_until_silence(wait_s)
                if wav is None:
                    break          # personne ne parle : retour en veille

                ui.mode = "thinking"
                t0 = time.time()
                if speaker_identifier:
                    speaker_started = time.time()
                    profile, reason, score = speaker_identifier.identify(wav)
                    context_reset = brain.set_current_speaker(profile, reason)
                    identity = profile["display_name"] if profile else "inconnu"
                    confidence = f" ({score:.2f})" if score is not None else ""
                    print(f"Locuteur : {identity}{confidence} — {reason} "
                          f"[identification {time.time() - speaker_started:.2f}s]")
                    if context_reset:
                        print("[Historique isolé : changement ou absence d'identification]")
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

                recent.append(brain.emotion)
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
                    emo = brain.emotion
                    if emo == "neutre":
                        emo = "neutre" if "tristesse" in recent else "joie"
                    ui.show_emotion(emo, hold=2.5)
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
    ap.add_argument("--tts-test", action="store_true", help="génère et lit les exemples vocaux de référence")
    ap.add_argument("--tts-test-voice", help="profil de voix à tester (par défaut : voix sauvegardée)")
    ap.add_argument("--tts-test-dir", default="tts-test-output", help="dossier racine des WAV de référence")
    ap.add_argument("--enroll-speaker", action="store_true",
                    help="enrôle un profil vocal local à partir de cinq phrases")
    ap.add_argument("--delete-speaker", help="supprime localement un profil vocal")
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
    if args.delete_speaker:
        profiles_path = cfg.get("speaker_identification", {}).get(
            "profiles_path", "data/speaker_profiles.json"
        )
        if not SpeakerProfileStore(profiles_path).remove(args.delete_speaker):
            sys.exit(f"Profil vocal introuvable : {args.delete_speaker}")
        print(f"Profil vocal supprimé : {args.delete_speaker}")
        return
    if args.enroll_speaker:
        speaker_cfg = cfg.get("speaker_identification", {})
        identifier = SpeakerIdentifier(
            speaker_cfg.get("model_path", "data/models/voxceleb_ECAPA512.onnx"),
            speaker_cfg.get("profiles_path", "data/speaker_profiles.json"),
            threshold=speaker_cfg.get("threshold", 0.30),
            ambiguity_margin=speaker_cfg.get("ambiguity_margin", 0.05),
            minimum_duration=speaker_cfg.get("minimum_duration_seconds", 3.0),
        )
        audio.start()
        try:
            enroll_speaker(audio, identifier, speaker_cfg)
        finally:
            audio.stop()
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
    if args.tts_test:
        cfg["tts"]["voice"] = settings.load().get("voice", cfg["tts"].get("voice"))
        tts = TTS(cfg["tts"], audio)
        if args.tts_test_voice and not tts.set_voice(args.tts_test_voice):
            sys.exit(f"Voix inconnue : {args.tts_test_voice}. Disponibles : {', '.join(tts.voice_names())}")
        run_dir = Path(args.tts_test_dir) / f"{time.strftime('%Y%m%d-%H%M%S')}-{tts.current}"
        run_dir.mkdir(parents=True, exist_ok=True)
        print(f"Test vocal {tts.engine} — voix : {tts.current}")
        print(f"Enregistrements WAV : {run_dir.resolve()}")
        for index, (name, text) in enumerate(TTS_TEST_CASES, 1):
            print(f"\n[{index}/{len(TTS_TEST_CASES)}] {name} : {text}")
            segments = tts.render(text)
            path = run_dir / f"{index:02d}-{name}.wav"
            save_wav(path, segments)
            audio.play_array(*join_audio_segments(segments))
            print(f"Fichier : {path}")
        print("\nÉcoute les WAV dans l'ordre et note le naturel, les coupures et l'intonation.")
        return

    key = os.getenv(cfg["api"]["api_key_env"])
    if not key:
        sys.exit("Clé d'API manquante : crée le fichier .env (voir .env.example).")

    # la voix choisie la dernière fois (settings.json) remplace celle de config.yaml
    cfg["tts"]["voice"] = settings.load().get("voice", cfg["tts"].get("voice"))

    client = OpenAI(base_url=cfg["api"]["base_url"], api_key=key)
    stt = STT(client, cfg["api"]["stt_model"], cfg["language"], cfg["api"].get("stt_prompt"))
    registry = ToolRegistry(cfg)
    robot_identity = cfg.get("robot", {})
    brain = Brain(client, cfg["llm"], cfg["api"]["llm_model"], tools=registry,
                  robot_identity=robot_identity)
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
    speaker_cfg = cfg.get("speaker_identification", {})
    speaker_identifier = None
    if speaker_cfg.get("enabled", False):
        speaker_identifier = SpeakerIdentifier(
            speaker_cfg.get("model_path", "data/models/voxceleb_ECAPA512.onnx"),
            speaker_cfg.get("profiles_path", "data/speaker_profiles.json"),
            threshold=speaker_cfg.get("threshold", 0.30),
            ambiguity_margin=speaker_cfg.get("ambiguity_margin", 0.05),
            minimum_duration=speaker_cfg.get("minimum_duration_seconds", 3.0),
        )

    audio.start()  # le micro écoute désormais en permanence
    if speaker_identifier is None:
        identity_status = "désactivée (speaker_identification.enabled=false)"
    elif len(speaker_identifier.profiles) < 2:
        identity_status = f"inactive ({len(speaker_identifier.profiles)} profil(s) ; 2 requis)"
    else:
        identity_status = (
            f"active ({len(speaker_identifier.profiles)} profils, "
            f"seuil : {speaker_identifier.threshold:.2f})"
        )
    wake_status = "manuel" if detector is None else (
        f"openWakeWord (seuil {detector.threshold:.2f}, "
        f"{detector.need} trames, RMS min. {detector.minimum_rms:.3f})"
    )
    print(f"Robot prêt. Voix actuelle : {tts.current} | Identification du locuteur : {identity_status} "
          f"| Réveil : {wake_status}")

    events, stop = queue.Queue(), threading.Event()
    worker = threading.Thread(target=robot_loop, daemon=True,
                              args=(cfg, audio, stt, brain, tts, filler, detector, events, ui, stop,
                                    speaker_identifier))
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
