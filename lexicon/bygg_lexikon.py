#!/usr/bin/env python3
"""
Läser SRT-filen för aktiv karaktär, skickar till Claude för slanganalys,
och sparar lexikon.json i karaktärens mapp.

Kör: python lexicon/bygg_lexikon.py
Karaktär styrs av config.toml → [bot] karaktär
"""

import json
import pathlib
import re
import tomllib
import anthropic

_ROT      = pathlib.Path(__file__).parent.parent
_LEX_ROT  = pathlib.Path(__file__).parent


def välj_karaktär() -> str:
    """Visar tillgängliga karaktärsmappar och låter användaren välja."""
    mappar = sorted(
        m.name for m in _LEX_ROT.iterdir()
        if m.is_dir() and not m.name.startswith(".")
    )
    if not mappar:
        raise FileNotFoundError(f"Inga karaktärsmappar hittades i {_LEX_ROT}")

    print("Tillgängliga karaktärer:")
    for i, namn in enumerate(mappar, 1):
        srt_antal = len(list((_LEX_ROT / namn).glob("*.srt")))
        har_lex   = "✓ lexikon" if (_LEX_ROT / namn / "lexikon.json").exists() else "  inget lexikon"
        print(f"  {i}. {namn}  ({srt_antal} srt-filer, {har_lex})")

    print()
    while True:
        val = input("Välj nummer: ").strip()
        if val.isdigit() and 1 <= int(val) <= len(mappar):
            return mappar[int(val) - 1]
        print(f"  Ange ett nummer mellan 1 och {len(mappar)}.")


_KARAKTÄR = välj_karaktär()
KAR_PATH  = _LEX_ROT / _KARAKTÄR
CHUNK_SIZE = 150

client = anthropic.Anthropic()


def hitta_srtar() -> list[pathlib.Path]:
    """Hittar alla SRT-filer i karaktärens mapp."""
    srtar = sorted(KAR_PATH.glob("*.srt"))
    if not srtar:
        raise FileNotFoundError(f"Inga SRT-filer hittades i {KAR_PATH}")
    return srtar


def extrahera_text(srt_innehall: str) -> list[str]:
    """Plockar ut bara replikerna, rensar bort tidskoder och radnummer."""
    repliker = []
    for rad in srt_innehall.splitlines():
        rad = rad.strip()
        if not rad:
            continue
        if re.match(r"^\d+$", rad):
            continue
        if re.match(r"^\d{2}:\d{2}:\d{2}", rad):
            continue
        rad = re.sub(r"<[^>]+>", "", rad).strip()
        if rad:
            repliker.append(rad)
    return repliker


def analysera_chunk(repliker: list[str], chunk_nr: int, totalt: int, filmtitel: str) -> dict:
    """Skickar en bit av dialogen till Claude för slanganalys."""
    dialog = "\n".join(repliker)
    print(f"  Analyserar del {chunk_nr}/{totalt} ({len(repliker)} repliker)...")

    svar = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2048,
        system=[{
            "type": "text",
            "text": """Du är expert på svensk 1930-40-tals stockholmska och pilsnerfilmer.
Din uppgift är att analysera filmdialoger och extrahera autentiskt slang,
ålderdomliga uttryck och typiska stockholmska drag från den epoken.""",
            "cache_control": {"type": "ephemeral"}
        }],
        messages=[{
            "role": "user",
            "content": f"""Analysera dessa repliker från pilsnerfilmen "{filmtitel}".

DIALOG:
{dialog}

Extrahera ALLA slangord, ålderdomliga uttryck, typiska fraser och stockholmska drag du hittar.
Returnera ENBART ett JSON-objekt i detta format (inga förklaringar utanför JSON):

{{
  "slangord": {{
    "ordet": "betydelse och ev. exempelmening från texten"
  }},
  "fraser": {{
    "frasen": "betydelse och ev. exempelmening"
  }},
  "utrop": {{
    "utropet": "när/hur det används"
  }},
  "exempelrepliker": [
    "de mest typiska och roliga replikerna ordagrant"
  ]
}}

Fokusera på ord som är specifika för epoken eller stockholmsk arbetarklassdialekt.
Inkludera bara ord som faktiskt finns i texten ovan."""
        }]
    )

    text = svar.content[0].text.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        text = match.group()
    return json.loads(text)


def sla_ihop(resultat: list[dict], filmtitel: str) -> dict:
    """Slår ihop alla chunk-resultat till ett lexikon."""
    lexikon = {
        "meta": {
            "källa": filmtitel,
            "karaktär": _KARAKTÄR,
            "beskrivning": "Autentiskt slang och uttryck från pilsnerfilmernas Stockholm",
            "metod": "Extraherat med Claude ur SRT-filen"
        },
        "slangord": {},
        "fraser": {},
        "utrop": {},
        "exempelrepliker": []
    }
    for r in resultat:
        lexikon["slangord"].update(r.get("slangord", {}))
        lexikon["fraser"].update(r.get("fraser", {}))
        lexikon["utrop"].update(r.get("utrop", {}))
        for rep in r.get("exempelrepliker", []):
            if rep not in lexikon["exempelrepliker"]:
                lexikon["exempelrepliker"].append(rep)
    return lexikon


def main():
    print(f"=== Lexikonbyggaren — {_KARAKTÄR} ===\n")

    srtar   = hitta_srtar()
    lex_fil = KAR_PATH / "lexikon.json"

    print(f"Hittade {len(srtar)} SRT-fil(er):")
    for s in srtar:
        print(f"  • {s.name}")
    print()

    # Läs och slå ihop alla SRT-filer till en stor repliklista
    alla_repliker = []
    for srt_fil in srtar:
        print(f"Läser {srt_fil.name}...")
        innehall = srt_fil.read_text(encoding="utf-8")
        rep = extrahera_text(innehall)
        print(f"  {len(rep)} repliker")
        alla_repliker.extend(rep)

    print(f"\nTotalt {len(alla_repliker)} repliker från alla filer.\n")

    chunks = [alla_repliker[i:i+CHUNK_SIZE] for i in range(0, len(alla_repliker), CHUNK_SIZE)]
    print(f"Delar upp i {len(chunks)} bitar à ~{CHUNK_SIZE} repliker.\n")

    källtitlar = ", ".join(s.stem for s in srtar)
    resultat = []
    for i, chunk in enumerate(chunks, 1):
        try:
            r = analysera_chunk(chunk, i, len(chunks), källtitlar)
            resultat.append(r)
        except (json.JSONDecodeError, Exception) as e:
            print(f"  ⚠ Fel i del {i}: {e} — hoppar över.")

    print(f"\nSlår ihop {len(resultat)} analyserade delar...")
    lexikon = sla_ihop(resultat, källtitlar)

    lex_fil.write_text(
        json.dumps(lexikon, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"\n✓ Klar! {lex_fil} uppdaterat med:")
    print(f"  {len(lexikon['slangord'])} slangord")
    print(f"  {len(lexikon['fraser'])} fraser")
    print(f"  {len(lexikon['utrop'])} utrop")
    print(f"  {len(lexikon['exempelrepliker'])} exempelrepliker")


if __name__ == "__main__":
    main()
