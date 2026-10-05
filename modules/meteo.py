"""Météo via Open-Meteo (gratuit, sans clé d'API, usage non commercial)."""
from datetime import date
from . import _http

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FILLERS = ['Un instant, je regarde la météo.', 'Je vérifie les prévisions, une seconde.']

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]
LABELS = ["Aujourd'hui", "Demain", "Après-demain"]

WMO = {0: "ciel dégagé", 1: "plutôt dégagé", 2: "partiellement nuageux", 3: "couvert",
       45: "brouillard", 48: "brouillard givrant",
       51: "bruine légère", 53: "bruine", 55: "bruine dense", 56: "bruine verglaçante", 57: "bruine verglaçante",
       61: "pluie faible", 63: "pluie modérée", 65: "pluie forte", 66: "pluie verglaçante", 67: "pluie verglaçante",
       71: "neige faible", 73: "neige modérée", 75: "neige forte", 77: "grains de neige",
       80: "averses faibles", 81: "averses", 82: "fortes averses", 85: "averses de neige", 86: "fortes averses de neige",
       95: "orage", 96: "orage avec grêle", 99: "violent orage avec grêle"}


def spec(cfg):
    default = cfg.get("location", {}).get("city", "Paris")
    return {
        "name": "get_weather",
        "description": ("Météo actuelle et prévisions pour aujourd'hui, demain et après-demain. "
                        f"Sans ville précisée, utilise la ville par défaut ({default})."),
        "parameters": {"type": "object",
                       "properties": {"city": {"type": "string", "description": "Nom de la ville, ex : Lyon. Facultatif."}},
                       "required": []},
    }


def _geocode(city, country_code):
    for cc in ([country_code, None] if country_code else [None]):
        params = {"name": city, "count": 1, "language": "fr", "format": "json"}
        if cc:
            params["countryCode"] = cc
        results = _http.get(GEO_URL, params, ttl=86400).json().get("results")
        if results:
            return results[0]
    return None


def _day_label(i, iso):
    d = date.fromisoformat(iso)
    label = LABELS[i] if i < len(LABELS) else ""
    return f"{label} ({JOURS[d.weekday()]} {d.day} {MOIS[d.month - 1]})"


def run(args, cfg):
    loc = cfg.get("location", {})
    city = (args.get("city") or "").strip() or loc.get("city", "Paris")
    place = _geocode(city, loc.get("country_code"))
    if not place:
        return f"Ville introuvable : {city}."

    data = _http.get(FORECAST_URL, {
        "latitude": place["latitude"], "longitude": place["longitude"],
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "auto", "forecast_days": 3,
    }, ttl=600).json()

    cur, daily = data["current"], data["daily"]
    name = place["name"] + (f" ({place['admin1']})" if place.get("admin1") else "")
    lines = [f"Météo pour {name}.",
             f"Maintenant : {round(cur['temperature_2m'])}°C (ressenti {round(cur['apparent_temperature'])}°C), "
             f"{WMO.get(cur['weather_code'], 'conditions variables')}, vent {round(cur['wind_speed_10m'])} km/h."]
    for i, iso in enumerate(daily["time"]):
        rain = daily["precipitation_probability_max"][i]
        rain_txt = f", risque de pluie {rain} %" if rain is not None else ""
        lines.append(f"{_day_label(i, iso)} : {WMO.get(daily['weather_code'][i], 'variable')}, "
                     f"min {round(daily['temperature_2m_min'][i])}°C, max {round(daily['temperature_2m_max'][i])}°C{rain_txt}.")
    return "\n".join(lines)
