"""Actualités via flux RSS (titres et résumés courts). Les flux se règlent dans config.yaml (section news)."""
import html
import re
import unicodedata
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

from . import _http

ATOM = "{http://www.w3.org/2005/Atom}"
MIN_DATE = datetime.min.replace(tzinfo=timezone.utc)
FILLERS = ['Un instant, je regarde les dernières nouvelles.', "Je consulte l'actualité, une seconde."]



def spec(cfg):
    cats = list(cfg.get("news", {}).get("feeds", {})) or ["une"]
    return {
        "name": "get_news",
        "description": ("Derniers titres de l'actualité (presse française). "
                        f"Catégories : {', '.join(cats)}. Un mot-clé peut filtrer les titres."),
        "parameters": {"type": "object", "properties": {
            "category": {"type": "string", "enum": cats, "description": "Catégorie (défaut : une)"},
            "keyword": {"type": "string", "description": "Mot-clé à chercher dans les titres, facultatif"}},
            "required": []},
    }


def _text(el, tag):
    found = el.find(tag)
    return (found.text or "").strip() if found is not None and found.text else ""


def _when(s):
    for parse in (parsedate_to_datetime, lambda x: datetime.fromisoformat(x.replace("Z", "+00:00"))):
        try:
            d = parse(s)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return MIN_DATE


def _clean(desc):
    desc = re.sub(r"<[^>]+>", " ", html.unescape(desc))
    desc = re.sub(r"\s+", " ", desc).strip()
    return desc[:180].rsplit(" ", 1)[0] + "..." if len(desc) > 180 else desc


def _parse(content, source):
    root = ET.fromstring(content)
    items = []
    for it in root.iter("item"):                     # RSS
        items.append({"title": _text(it, "title"), "desc": _clean(_text(it, "description")),
                      "when": _when(_text(it, "pubDate")), "source": source})
    for it in root.iter(f"{ATOM}entry"):             # Atom
        items.append({"title": _text(it, f"{ATOM}title"), "desc": _clean(_text(it, f"{ATOM}summary")),
                      "when": _when(_text(it, f"{ATOM}updated")), "source": source})
    return [i for i in items if i["title"]]


def _source(url):
    return urlparse(url).netloc.replace("www.", "")


def _norm(s):
    """Minuscules sans accents : 'Animé' et 'anime' deviennent identiques."""
    s = unicodedata.normalize("NFD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _fetch(url):
    try:
        return _parse(_http.get(url, ttl=300).content, _source(url))
    except Exception:
        return None


def _gather(urls):
    """Télécharge plusieurs flux en parallèle. Retourne (articles, nombre de flux en échec)."""
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(_fetch, urls))
    return [i for r in results if r for i in r], sum(1 for r in results if r is None)


def _rank(items, keyword):
    """Supprime les doublons, trie du plus récent au plus ancien, filtre par mot-clé."""
    seen, unique = set(), []
    for it in sorted(items, key=lambda x: x["when"], reverse=True):
        key = it["title"].lower()
        if key not in seen:
            seen.add(key)
            unique.append(it)
    if keyword:
        k = _norm(keyword)
        unique = [i for i in unique if k in _norm(i["title"] + " " + i["desc"])]
    return unique


def run(args, cfg):
    ncfg = cfg.get("news", {})
    feeds = ncfg.get("feeds", {})
    cat = args.get("category") or "une"
    urls = feeds.get(cat) or feeds.get("une") or next(iter(feeds.values()), [])
    keyword = (args.get("keyword") or "").strip()
    limit = int(ncfg.get("max_items", 5))

    items, _ = _gather(urls)
    if not items:
        return "[Actualités indisponibles : flux inaccessibles.]"
    unique, scope = _rank(items, keyword), f"catégorie {cat}"

    if keyword and not unique:  # rien dans la catégorie : on élargit à tous les flux
        all_urls = list(dict.fromkeys(u for lst in feeds.values() for u in lst))
        items, _ = _gather(all_urls)
        unique, scope = _rank(items, keyword), "toutes catégories"
        if not unique:
            return f"[Aucun article récent sur « {keyword} » dans les flux de presse générale (France Info, Le Monde).]"

    lines = [f"Actualités, {scope} :"]
    for i, it in enumerate(unique[:limit], 1):
        extra = f" — {it['desc']}" if it["desc"] else ""
        lines.append(f"{i}. {it['title']}{extra} (source : {it['source']})")
    return "\n".join(lines)


def check_feeds(cfg):
    """Teste chaque flux (utilisé par : python main.py --tools)."""
    for cat, urls in cfg.get("news", {}).get("feeds", {}).items():
        for url in urls:
            try:
                n = len(_parse(_http.get(url, ttl=0).content, _source(url)))
                print(f"  OK     [{cat}] {url} ({n} articles)")
            except Exception as e:
                print(f"  ÉCHEC  [{cat}] {url} -> {type(e).__name__}")
