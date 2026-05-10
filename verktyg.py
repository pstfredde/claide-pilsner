"""
Verktyg som Gugge kan använda för att hämta information från omvärlden.
Tre verktyg: webbsökning, väder och nyheter.
"""

import json
import requests
import feedparser
from duckduckgo_search import DDGS


# ── Verktygsdefinitioner för Claude API ──────────────────────────────────────

VERKTYG = [
    {
        "name": "sok_pa_natet",
        "description": (
            "Sök efter information på internet. Använd när användaren frågar om "
            "fakta, personer, händelser eller annat som kräver aktuell information."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fraga": {
                    "type": "string",
                    "description": "Sökfrågan på svenska eller engelska"
                }
            },
            "required": ["fraga"]
        }
    },
    {
        "name": "hamta_vader",
        "description": (
            "Hämtar aktuellt väder och prognos för en stad. Använd när användaren "
            "frågar om väder, temperatur, regn, sol eller liknande."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "stad": {
                    "type": "string",
                    "description": "Stadens namn, t.ex. 'Stockholm', 'Göteborg'"
                }
            },
            "required": ["stad"]
        }
    },
    {
        "name": "hamta_nyheter",
        "description": (
            "Hämtar de senaste nyheterna från svenska medier. Använd när användaren "
            "frågar om nyheter, vad som hänt, aktuella händelser."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "amne": {
                    "type": "string",
                    "description": "Valfritt ämne att filtrera på, t.ex. 'sport', 'ekonomi'. Tom sträng ger toppnyheter."
                }
            },
            "required": ["amne"]
        }
    }
]


# ── Verktygsfunktioner ────────────────────────────────────────────────────────

def sök_på_nätet(fråga: str) -> str:
    """Söker med DuckDuckGo och returnerar de 5 bästa träffarna."""
    try:
        with DDGS() as ddgs:
            träffar = list(ddgs.text(fråga, max_results=5))
        if not träffar:
            return "Inga sökresultat hittades."
        rader = []
        for t in träffar:
            rader.append(f"• {t['title']}\n  {t['body']}")
        return "\n\n".join(rader)
    except Exception as e:
        return f"Sökning misslyckades: {e}"


def hämta_väder(stad: str) -> str:
    """Hämtar väder via Nominatim (koordinater) + yr.no (prognos)."""
    try:
        # Steg 1: koordinater via OpenStreetMap
        geo = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": stad, "format": "json", "limit": 1},
            headers={"User-Agent": "pilsner-bot/1.0"},
            timeout=5
        ).json()

        if not geo:
            return f"Kunde inte hitta koordinater för {stad}."

        lat = float(geo[0]["lat"])
        lon = float(geo[0]["lon"])
        plats = geo[0].get("display_name", stad).split(",")[0]

        # Steg 2: väderprognos via yr.no
        väder = requests.get(
            f"https://api.met.no/weatherapi/locationforecast/2.0/compact",
            params={"lat": round(lat, 4), "lon": round(lon, 4)},
            headers={"User-Agent": "pilsner-bot/1.0"},
            timeout=5
        ).json()

        nu = väder["properties"]["timeseries"][0]["data"]
        temp     = nu["instant"]["details"]["air_temperature"]
        vind     = nu["instant"]["details"]["wind_speed"]
        nästa    = nu.get("next_1_hours") or nu.get("next_6_hours") or {}
        symbol   = nästa.get("summary", {}).get("symbol_code", "okänt")
        nederbörd = nästa.get("details", {}).get("precipitation_amount", 0)

        # Översätt symbol till svenska
        symboler = {
            "clearsky": "klart", "fair": "mestadels klart",
            "partlycloudy": "halvklart", "cloudy": "mulet",
            "rain": "regn", "lightrain": "lätt regn",
            "heavyrain": "kraftigt regn", "snow": "snö",
            "lightsnow": "lätt snö", "sleet": "snöblandat regn",
            "fog": "dimma", "thunder": "åska"
        }
        vädertyp = next((v for k, v in symboler.items() if k in symbol), symbol)

        svar = f"{plats}: {temp}°C, {vädertyp}, vind {vind} m/s"
        if nederbörd > 0:
            svar += f", nederbörd {nederbörd} mm"
        return svar

    except Exception as e:
        return f"Kunde inte hämta väder: {e}"


def hämta_nyheter(ämne: str = "") -> str:
    """Hämtar nyheter från SVT via RSS."""
    try:
        url = "https://www.svt.se/nyheter/rss.xml"
        feed = feedparser.parse(url)

        poster = feed.entries[:15]

        if ämne:
            filtrerade = [
                p for p in poster
                if ämne.lower() in (p.get("title", "") + p.get("summary", "")).lower()
            ]
            poster = filtrerade[:5] if filtrerade else poster[:5]
        else:
            poster = poster[:5]

        if not poster:
            return "Inga nyheter hittades."

        rader = []
        for p in poster:
            rubrik  = p.get("title", "")
            summary = p.get("summary", "")
            rader.append(f"• {rubrik}: {summary}")
        return "\n".join(rader)

    except Exception as e:
        return f"Kunde inte hämta nyheter: {e}"


# ── Dispatcher ────────────────────────────────────────────────────────────────

def kör_verktyg(namn: str, indata: dict) -> str:
    """Kör rätt verktygsfunktion baserat på namn."""
    if namn == "sok_pa_natet":
        return sök_på_nätet(indata["fraga"])
    elif namn == "hamta_vader":
        return hämta_väder(indata["stad"])
    elif namn == "hamta_nyheter":
        return hämta_nyheter(indata.get("amne", ""))
    else:
        return f"Okänt verktyg: {namn}"
