"""Mot d'activation : le robot écoute en permanence, mais ne s'éveille que sur son 'mot' ou son nom.

Détecteurs :
  - "manual"       : pas de détection par la voix ; on déclenche avec Entrée (console) ou Espace (fenêtre)
  - "openwakeword" : détection locale, gratuite, hors-ligne (modèles anglais prêts à l'emploi ; modèle perso possible)
Ajouter un autre détecteur (Porcupine...) = une classe avec process(bloc) -> bool."""
import queue

import numpy as np


class OpenWakeWordDetector:
    def __init__(self, cfg: dict):
        import openwakeword
        from openwakeword.model import Model

        names = cfg.get("models") or ["hey_jarvis"]
        try:
            openwakeword.utils.download_models()   # ne télécharge que ce qui manque (internet requis la 1re fois)
        except Exception:
            pass
        try:
            self.model = Model(wakeword_models=names, inference_framework="onnx")
        except TypeError:
            self.model = Model(wakeword_models=names)
        self.threshold = float(cfg.get("threshold", 0.5))
        self.need = int(cfg.get("consecutive_frames", 2))
        self.hits = 0
        self.last_score = 0.0

    def reset(self):
        self.hits = 0
        if hasattr(self.model, "reset"):
            self.model.reset()

    def process(self, block) -> bool:
        pcm = (np.clip(block, -1, 1) * 32767).astype(np.int16)
        scores = self.model.predict(pcm)
        self.last_score = float(max(scores.values())) if scores else 0.0
        self.hits = self.hits + 1 if self.last_score >= self.threshold else 0
        if self.hits >= self.need:
            self.reset()
            return True
        return False


def make_detector(cfg: dict):
    """Retourne un détecteur, ou None (mode manuel) si indisponible, avec un message clair."""
    if cfg.get("mode", "manual") != "openwakeword":
        return None
    try:
        return OpenWakeWordDetector(cfg)
    except ImportError:
        print("[mot d'activation indisponible : pip install -r requirements-wake.txt -> mode manuel]")
    except Exception as e:
        print(f"[mot d'activation : échec ({type(e).__name__}: {e}) -> mode manuel]")
    return None


def wait_for_trigger(audio, detector, events: queue.Queue, stop):
    """Bloque jusqu'à : le mot d'activation, une touche (événement 'wake'), une commande ou l'arrêt.
    Retourne un tuple d'événement, ou None si on arrête."""
    if detector:
        detector.reset()
    while not stop.is_set():
        try:
            return events.get_nowait()
        except queue.Empty:
            pass
        try:
            block = audio.read_block(timeout=0.1)
        except queue.Empty:
            continue
        if detector and detector.process(block):
            return ("wake", "word")
    return None
