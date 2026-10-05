"""Outils du robot. Chaque fichier de ce dossier (sauf ceux qui commencent par _) est un outil.

Pour ajouter un outil, créer modules/mon_outil.py avec deux fonctions :
    FILLERS = ["Un instant..."]   (facultatif) phrases dites si l'outil est lent
    spec(cfg) -> dict   description de l'outil pour le LLM (nom, description, paramètres)
    run(args, cfg) -> str   exécute l'outil et renvoie un TEXTE que le LLM va résumer à voix haute
Il est détecté automatiquement : aucune autre modification nécessaire.
"""
import importlib
import json
import pkgutil
import random


class ToolRegistry:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._mods = {}
        self._specs = []
        for info in pkgutil.iter_modules(__path__):
            if info.name.startswith("_"):
                continue
            mod = importlib.import_module(f"{__name__}.{info.name}")
            if hasattr(mod, "spec") and hasattr(mod, "run"):
                s = mod.spec(cfg)
                self._mods[s["name"]] = mod
                self._specs.append({"type": "function", "function": s})

    def specs(self):
        return self._specs

    def names(self):
        return list(self._mods)

    def filler(self, name: str):
        """Une phrase d'attente au hasard pour cet outil (ou None)."""
        phrases = getattr(self._mods.get(name), "FILLERS", None)
        return random.choice(phrases) if phrases else None

    def all_fillers(self):
        return [p for m in self._mods.values() for p in getattr(m, "FILLERS", [])]

    def call(self, name: str, arguments: str) -> str:
        mod = self._mods.get(name)
        if mod is None:
            return f"[Outil inconnu : {name}]"
        try:
            args = json.loads(arguments) if arguments and arguments.strip() else {}
            if not isinstance(args, dict):
                args = {}
        except ValueError:
            args = {}
        try:
            return str(mod.run(args, self.cfg))
        except Exception as e:  # un outil en panne ne doit jamais faire planter le robot
            return f"[Erreur de l'outil {name} : {type(e).__name__}. Information indisponible.]"
