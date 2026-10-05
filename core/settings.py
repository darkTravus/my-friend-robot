"""Réglages choisis par l'utilisateur (ex : voix), sauvegardés dans settings.json.
Séparés de config.yaml : config.yaml = réglages techniques, settings.json = préférences modifiables
(plus tard, l'interface du téléphone écrira ici)."""
import json
import os

PATH = "settings.json"


def load() -> dict:
    if os.path.exists(PATH):
        try:
            with open(PATH, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
    return {}


def save(**changes):
    data = load()
    data.update(changes)
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
