"""État partagé entre le robot (qui écrit) et l'affichage (qui lit)."""
import time


class UIState:
    """mode : 'idle' (veille) | 'listening' (écoute) | 'thinking' (réflexion) | 'speaking' (parole)
    emotion : neutre | joie | amusement | surprise | curiosite | tristesse | doute"""

    def __init__(self):
        self._mode = "idle"
        self.emotion = "neutre"
        self.emotion_until = 0.0      # l'émotion reste affichée jusqu'à cet instant, même après la parole
        self.idle_since = time.time()

    @property
    def mode(self):
        return self._mode

    @mode.setter
    def mode(self, value):
        if value == "idle" and self._mode != "idle":
            self.idle_since = time.time()
        self._mode = value

    def show_emotion(self, name: str, hold: float = 0.0):
        """Affiche une émotion ; hold = secondes pendant lesquelles elle reste visible hors de la parole."""
        self.emotion = name
        self.emotion_until = time.time() + hold

    def view(self, now: float, sleep_after: float = 90.0):
        """Retourne (mode, émotion) à dessiner à cet instant."""
        mode, emo = self._mode, self.emotion
        if mode == "idle" and now >= self.emotion_until and now - self.idle_since > sleep_after:
            return mode, "sommeil"
        if mode == "speaking" or now < self.emotion_until:
            return mode, emo
        return mode, "neutre"
