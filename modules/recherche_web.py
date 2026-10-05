"""Recherche sur Internet. Deux fournisseurs, au choix dans config.yaml (web_search.provider) :
  - "ddgs"   : DuckDuckGo & co via le paquet ddgs. Aucune clé, mais non officiel (quotas possibles).
  - "tavily" : API conçue pour les LLM, plus fiable. Clé dans .env (TAVILY_API_KEY)."""
import os
from urllib.parse import urlparse

import requests

FILLERS = ["Un instant s'il te plaît, le temps que je fasse une recherche.",
           "Je cherche ça sur internet, une seconde.",
           "Laisse-moi faire une petite recherche."]
UNREADABLE = ("msn.com", "facebook.com", "instagram.com", "x.com", "twitter.com", "youtube.com", "tiktok.com")
SEEN_URLS = set()  # URL renvoyées par les recherches : seules ces pages pourront être lues


def spec(cfg):
    return {
        "name": "search_web",
        "description": ("Recherche sur Internet. À utiliser pour toute question factuelle que tu ne connais pas ou qui "
                        "peut avoir changé : sorties récentes (animés, films, jeux), personnalités, événements, "
                        "prix, résultats. Ne pas utiliser pour la météo ni pour les titres généraux de l'actualité "
                        "(outils dédiés)."),
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "Requête de recherche courte et précise, en français ou en anglais"},
            "recent": {"type": "boolean", "description": "true uniquement pour des nouvelles datant de quelques jours ; false pour le reste (listes, fiches, calendriers)"}},
            "required": ["query"]},
    }


def _domain(url):
    return urlparse(url or "").netloc.replace("www.", "")


def _search_ddgs(query, recent, wcfg):
    from ddgs import DDGS  # import tardif : le module se charge même si le paquet manque
    n, region = int(wcfg.get("max_results", 5)), wcfg.get("region", "fr-fr")
    ddgs = DDGS(timeout=8)
    if recent:
        try:
            raw = ddgs.news(query, region=region, max_results=n)
        except Exception:
            raw = ddgs.text(query, region=region, max_results=n, timelimit="m")
    else:
        raw = ddgs.text(query, region=region, max_results=n)
    return [{"title": r.get("title", ""), "text": r.get("body", ""), "url": r.get("href") or r.get("url", "")}
            for r in raw]


def _search_tavily(query, recent, wcfg):
    key = os.getenv(wcfg.get("tavily_api_key_env", "TAVILY_API_KEY"))
    if not key:
        raise RuntimeError("clé Tavily manquante")
    resp = requests.post("https://api.tavily.com/search",
                         headers={"Authorization": f"Bearer {key}"},
                         json={"query": query, "max_results": int(wcfg.get("max_results", 5)),
                               "search_depth": "basic", "topic": "news" if recent else "general"},
                         timeout=15)
    resp.raise_for_status()
    return [{"title": r.get("title", ""), "text": r.get("content", ""), "url": r.get("url", "")}
            for r in resp.json().get("results", [])]


PROVIDERS = {"ddgs": _search_ddgs, "tavily": _search_tavily}


def run(args, cfg):
    query = (args.get("query") or "").strip()
    if not query:
        return "Aucune requête fournie."
    wcfg = cfg.get("web_search", {})
    provider = wcfg.get("provider", "ddgs")
    try:
        results = PROVIDERS[provider](query, bool(args.get("recent")), wcfg)
    except ImportError:
        return "[Recherche indisponible : paquet ddgs manquant.]"
    except Exception as e:
        print(f"  [recherche web : échec {provider} -> {type(e).__name__}: {e}]")
        return "[Recherche indisponible pour le moment.]"

    results = [r for r in results if r["title"] or r["text"]]
    if not results:
        return f"[Aucun résultat pour « {query} ».]"
    lines = [f"Résultats de recherche pour « {query} » (réponds uniquement d'après ces extraits ; si les détails manquent, utilise read_webpage sur l'URL la plus pertinente) :"]
    for i, r in enumerate(results, 1):
        text = " ".join(r["text"].split())[:300]
        host = _domain(r["url"])
        if r["url"] and not any(host == d or host.endswith("." + d) for d in UNREADABLE):
            SEEN_URLS.add(r["url"])
            where = f"URL : {r['url']}"
        else:
            where = "(page non lisible par read_webpage)"
        lines.append(f"{i}. {r['title']} — {text} (source : {host}) {where}")
    return "\n".join(lines)
