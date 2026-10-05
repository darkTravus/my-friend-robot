"""Petit utilitaire HTTP partagé par les outils : en-tête User-Agent, délai maximum, cache mémoire."""
import time
import requests

_cache = {}
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RobotCompagnon/0.1)"}


def get(url, params=None, ttl=300, timeout=8):
    key = (url, tuple(sorted((params or {}).items())))
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    _cache[key] = (now, r)
    return r
