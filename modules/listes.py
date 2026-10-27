"""Gestion de listes nommées conservées localement."""
import hashlib
import json
import re
import tempfile
import unicodedata
from pathlib import Path


def spec(cfg):
    return {
        "name": "manage_list",
        "description": (
            "Gère les listes personnelles persistantes. Utilise cette fonction pour ajouter un élément, "
            "consulter une liste, supprimer un élément précis, lister les noms des listes ou exporter "
            "une liste en Markdown ou en texte. Une liste est créée automatiquement lors du premier ajout. "
            "Pour supprimer un élément, fournis son texte exact."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "show", "remove", "list", "export"],
                    "description": "Action à effectuer.",
                },
                "list_name": {"type": "string", "description": "Nom de la liste, par exemple courses ou animés."},
                "item": {"type": "string", "description": "Élément à ajouter ou à supprimer."},
                "format": {
                    "type": "string",
                    "enum": ["md", "txt"],
                    "description": "Format d'export (défaut : md).",
                },
            },
            "required": ["action"],
        },
    }


def _data_dir(cfg):
    return Path(cfg.get("lists", {}).get("data_dir", "data"))


def _load(path):
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as source:
        data = json.load(source)
    if (not isinstance(data, dict)
            or any(not isinstance(name, str) or not name.strip()
                   or not isinstance(items, list)
                   or any(not isinstance(item, str) or not item.strip() for item in items)
                   for name, items in data.items())):
        raise ValueError("Le fichier des listes a un format invalide.")
    return data


def _save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False) as target:
        json.dump(data, target, ensure_ascii=False, indent=2)
        target.write("\n")
        temporary = Path(target.name)
    try:
        temporary.replace(path)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def _find_key(data, name):
    normalized = name.strip().casefold()
    return next((key for key in data if key.casefold() == normalized), None)


def _required_text(args, key):
    value = args.get(key)
    return value.strip() if isinstance(value, str) else ""


def _export_name(name):
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:48] or "liste"
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:8]
    return f"{slug}-{digest}"


def _render(name, items, file_format):
    if file_format == "txt":
        return f"{name}\n" + "".join(f"- {item}\n" for item in items)
    return f"# {name}\n\n" + "".join(f"- {item}\n" for item in items)


def run(args, cfg):
    action = _required_text(args, "action")
    if action not in {"add", "show", "remove", "list", "export"}:
        return "[Action de liste invalide.]"

    data_dir = _data_dir(cfg)
    data_path = data_dir / "lists.json"
    data = _load(data_path)

    if action == "list":
        names = sorted(data, key=str.casefold)
        return "Listes enregistrées : " + ", ".join(names) if names else "Aucune liste enregistrée."

    name = _required_text(args, "list_name")
    if not name:
        return "[Nom de liste manquant.]"
    key = _find_key(data, name)

    if action == "add":
        item = _required_text(args, "item")
        if not item:
            return "[Élément à ajouter manquant.]"
        if key is None:
            key = name
            data[key] = []
        if any(existing.casefold() == item.casefold() for existing in data[key]):
            return f"« {item} » est déjà dans la liste {key}."
        data[key].append(item)
        _save(data_path, data)
        return f"« {item} » a été ajouté à la liste {key}."

    if key is None:
        return f"La liste {name} n'existe pas."
    items = data[key]

    if action == "show":
        if not items:
            return f"La liste {key} est vide."
        return f"Liste {key} :\n" + "\n".join(f"- {item}" for item in items)

    if action == "remove":
        item = _required_text(args, "item")
        if not item:
            return "[Élément à supprimer manquant.]"
        match = next((existing for existing in items if existing.casefold() == item.casefold()), None)
        if match is None:
            return f"« {item} » n'est pas dans la liste {key}."
        items.remove(match)
        _save(data_path, data)
        return f"« {match} » a été supprimé de la liste {key}."

    file_format = _required_text(args, "format") or "md"
    if file_format not in {"md", "txt"}:
        return "[Format d'export invalide : utilise md ou txt.]"
    export_dir = data_dir / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    export_path = export_dir / f"{_export_name(key)}.{file_format}"
    export_path.write_text(_render(key, items, file_format), encoding="utf-8")
    return f"Liste {key} exportée en {file_format.upper()} dans {export_path}."
