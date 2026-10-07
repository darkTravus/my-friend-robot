"""Intelligence de conversation, 100 % locale et ultra légère (expressions régulières, aucun modèle) :
  - lecture de l'étiquette d'émotion et de fin donnée par le LLM  ->  "[joie] Super !"  /  "[joie][fin] À bientôt !"
  - émotion de secours si le LLM a oublié l'étiquette
  - détection de la fin de conversation côté utilisateur ("merci, à plus tard")
  - filtre des phrases fantômes que Whisper invente sur du bruit ou une télé"""
import re
import unicodedata

EMOTIONS = ("neutre", "joie", "amusement", "surprise", "curiosite", "tristesse", "doute")
_ALIASES = {"curieux": "curiosite", "content": "joie", "heureux": "joie", "enthousiaste": "joie",
            "drole": "amusement", "rire": "amusement", "triste": "tristesse", "desole": "tristesse",
            "empathie": "tristesse", "etonne": "surprise", "perplexe": "doute", "incertain": "doute",
            "calme": "neutre"}
_LEADING_TAGS = re.compile(r"^\s*((?:\[[^\]]{1,20}\]\s*)+)")
_ANY_TAG = re.compile(r"\[[^\]]{1,20}\]")


def norm(s: str) -> str:
    """minuscules, sans accents ni ponctuation superflue."""
    s = unicodedata.normalize("NFD", s.lower().replace("’", "'"))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9' ?]", " ", s).strip()


def parse_reply(raw: str):
    """Retourne (texte à dire, émotion, fin_de_conversation). Le texte ne contient jamais d'étiquette."""
    emotion, end, text = None, False, raw
    m = _LEADING_TAGS.match(raw)
    if m:
        for tag in re.findall(r"\[([^\]]+)\]", m.group(1)):
            t = norm(tag)
            if t == "fin":
                end = True
            elif t in EMOTIONS:
                emotion = t
            elif t in _ALIASES:
                emotion = _ALIASES[t]
        text = raw[m.end():]
    text = _ANY_TAG.sub("", text).strip()   # étiquettes égarées en cours de phrase
    return text, emotion or guess_emotion(text), end


_RULES = [
    ("amusement", r"\b(ha ?ha|haha|mdr|lol|droles?|rigol|marrant|blague)"),
    ("tristesse", r"\b(desole|malheureusement|triste|dommage|courage|navre|condoleances)"),
    ("doute", r"(je ne sais pas|aucun|pas trouve|pas pu|indisponible|rien trouve|pas sur|pas certain|je n'ai pas d'info)"),
    ("surprise", r"\b(wow|waouh|incroyable|ca alors|quelle surprise|vraiment ?\?|oh la la)"),
    ("joie", r"\b(super|genial|bravo|felicitations|avec plaisir|excellent|parfait|youpi|merveilleux|content|ravi)"),
]


def guess_emotion(text: str) -> str:
    """Émotion de secours à partir du texte (si le LLM a oublié l'étiquette)."""
    t = norm(text)
    for emotion, pattern in _RULES:
        if re.search(pattern, t):
            return emotion
    return "curiosite" if text.rstrip().endswith("?") else "neutre"


_END = re.compile(
    r"(^|\b)(merci|c'est tout|c'est bon|ca ira|ca sera tout|au revoir|a plus|a tout a l'heure|a bientot|a demain|"
    r"bonne nuit|bonne soiree|bonne journee|tchao|ciao|j'ai fini|laisse tomber|on se reparle|stop)\b")
_CONTINUE = re.compile(r"\b(et|mais|aussi|encore|dis|dis moi|peux tu|pourrais tu|quel|quelle|quels|quelles|comment|pourquoi|combien|ou)\b")


def user_wants_to_end(text: str) -> bool:
    """Phrase courte de clôture ("merci", "ok c'est bon", "à plus tard") sans nouvelle demande."""
    t = norm(text)
    words = t.replace("?", " ").split()
    if not words or len(words) > 6 or "?" in t:
        return False
    return bool(_END.search(t)) and not _CONTINUE.search(t)


_GHOSTS = ("sous titr", "sous-titr", "merci d'avoir regarde", "abonnez vous", "amara", "n'oubliez pas de vous abonner",
           "a la prochaine pour une nouvelle video")


def is_noise_transcript(text: str) -> bool:
    """Phrases que Whisper invente quand il n'y a que du bruit (sous-titres, 'merci d'avoir regardé'...)."""
    t = norm(text)
    return len(t) < 2 or any(g in t for g in _GHOSTS)
