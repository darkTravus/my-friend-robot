"""Phrases d'attente ("Un instant, je fais une recherche...") dites quand un outil est lent.

- Les phrases sont définies par chaque outil (variable FILLERS dans modules/xxx.py).
- Elles sont synthétisées à l'avance (en arrière-plan) : la lecture est alors instantanée.
- Une seule phrase d'attente par question, et seulement si l'outil dépasse delay_seconds."""
import threading


class Filler:
    def __init__(self, tts, registry, cfg: dict | None = None, ui=None, extra_phrases=None):
        cfg = cfg or {}
        self.tts, self.registry, self.ui = tts, registry, ui
        self.extra = list(extra_phrases or [])   # ex. réponses de réveil ("Oui ?") : même mécanisme de pré-synthèse
        self.enabled = cfg.get("enabled", True)
        self.delay = float(cfg.get("delay_seconds", 0.7))
        self._thread = None
        self._played = False

    def warm(self):
        """Prépare les phrases avec la voix actuelle (à rappeler après un changement de voix)."""
        phrases = self.extra + (self.registry.all_fillers() if self.enabled else [])
        if phrases:
            self.tts.warm(phrases)

    def start_turn(self):
        self._played, self._thread = False, None

    def on_slow(self, tool_name: str):
        """Appelé par le cerveau quand un outil dépasse le délai. Ne bloque pas."""
        if not self.enabled or self._played:
            return
        phrase = self.registry.filler(tool_name)
        if not phrase:
            return
        self._played = True
        self._thread = threading.Thread(target=self._say, args=(phrase,), daemon=True)
        self._thread.start()

    def _say(self, phrase):
        if self.ui:
            self.ui.mode = "speaking"      # les yeux s'animent pendant la phrase d'attente
        try:
            self.tts.play_cached(phrase)
        finally:
            if self.ui:
                self.ui.mode = "thinking"

    def wait(self):
        """À appeler avant de lire la vraie réponse : évite que deux sons se chevauchent."""
        if self._thread:
            self._thread.join()
