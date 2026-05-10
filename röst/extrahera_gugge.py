#!/usr/bin/env python3
"""
Identifierar Gugges repliker i SRT-filen med hjälp av Claude,
klipper ut dem ur MKV-filen med ffmpeg och slår ihop till
en ren ljudfil för ElevenLabs röstkloning.

Kör: python extrahera_gugge.py
"""

import json
import pathlib
import re
import subprocess
import anthropic

KATALOG    = pathlib.Path(__file__).parent
SRT_FIL    = KATALOG / "Springpojkar är vi allihopa.srt"
MKV_FIL    = KATALOG / "Springpojkar är vi allihopa 1941.mkv"
UT_KATALOG = KATALOG / "gugge_klipp"
SLUTFIL    = KATALOG / "gugge_roster.mp3"

client = anthropic.Anthropic()


# ── 1. Parsa SRT ──────────────────────────────────────────────────────────────

def parsa_srt(srt_text: str) -> list[dict]:
    """Returnerar lista med {nr, start, slut, text} för varje replik."""
    block_re = re.compile(
        r"(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n([\s\S]*?)(?=\n\n|\Z)",
        re.MULTILINE
    )
    resultat = []
    for m in block_re.finditer(srt_text):
        text = re.sub(r"<[^>]+>", "", m.group(4)).strip().replace("\n", " ")
        if text:
            resultat.append({
                "nr":    int(m.group(1)),
                "start": m.group(2),
                "slut":  m.group(3),
                "text":  text,
            })
    return resultat


def tid_till_sekunder(tid: str) -> float:
    """'00:01:23,456' → 83.456"""
    h, m, rest = tid.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


# ── 2. Identifiera Gugges repliker med Claude ─────────────────────────────────

def hitta_gugge_repliker(repliker: list[dict]) -> list[int]:
    """Skickar replikerna i bitar till Claude och returnerar nr på Gugges rader."""
    CHUNK = 80
    gugge_nr = []

    chunks = [repliker[i:i+CHUNK] for i in range(0, len(repliker), CHUNK)]
    print(f"Analyserar {len(repliker)} repliker i {len(chunks)} omgångar...")

    for i, chunk in enumerate(chunks, 1):
        print(f"  Omgång {i}/{len(chunks)}...")

        dialog = "\n".join(
            f"[{r['nr']}] {r['text']}" for r in chunk
        )

        svar = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=1024,
            system=[{
                "type": "text",
                "text": (
                    "Du är expert på svenska pilsnerfilmer från 1940-talet. "
                    "Filmen är 'Springpojkar är vi allihopa' (1941). "
                    "Gugge är springpojken/cykelbudet på AB Delikatesser — "
                    "ung, snabb i munnen, stockholmsk arbetarklass. "
                    "Han kallas ibland 'Gugge' av andra karaktärer."
                ),
                "cache_control": {"type": "ephemeral"}
            }],
            messages=[{
                "role": "user",
                "content": (
                    f"Här är repliker från filmen med radnummer inom hakparentes:\n\n{dialog}\n\n"
                    "Vilka av dessa repliker talar troligen GUGGE? "
                    "Tänk på: vem tilltalar vem, vem svarar på vad, Gugges typiska tonfall. "
                    "Returnera ENBART ett JSON-objekt: {\"gugge_nr\": [lista med radnummer]}"
                )
            }]
        )

        text = svar.content[0].text.strip()
        match = re.search(r"\{.*?\}", text, re.DOTALL)
        if match:
            data = json.loads(match.group())
            gugge_nr.extend(data.get("gugge_nr", []))

    return sorted(set(gugge_nr))


# ── 3. Klipp ut ljud med ffmpeg ───────────────────────────────────────────────

def klipp_ut(repliker_dict: dict, gugge_nr: list[int]) -> list[pathlib.Path]:
    """Klipper ut varje Gugge-replik som en separat mp3-fil."""
    UT_KATALOG.mkdir(exist_ok=True)
    filer = []
    PADDING = 0.15  # sekunder extra runt klippet

    print(f"\nKlipper ut {len(gugge_nr)} repliker ur MKV-filen...")

    for idx, nr in enumerate(gugge_nr):
        r = repliker_dict[nr]
        start = max(0.0, tid_till_sekunder(r["start"]) - PADDING)
        slut  = tid_till_sekunder(r["slut"]) + PADDING
        varaktighet = slut - start

        ut_fil = UT_KATALOG / f"gugge_{idx:04d}.mp3"

        subprocess.run([
            "ffmpeg", "-y",
            "-ss", str(start),
            "-i", str(MKV_FIL),
            "-t", str(varaktighet),
            "-vn",                    # bara ljud
            "-af", "afftdn=nf=-25",   # lätt brusreducering
            "-ar", "22050",           # samplingfrekvens
            "-ac", "1",               # mono
            "-q:a", "4",              # MP3-kvalitet
            str(ut_fil)
        ], capture_output=True)

        if ut_fil.exists() and ut_fil.stat().st_size > 1000:
            filer.append(ut_fil)

    print(f"  {len(filer)} klipp sparade i {UT_KATALOG.name}/")
    return filer


def sla_ihop(filer: list[pathlib.Path]) -> None:
    """Slår ihop alla klipp till en enda mp3-fil."""
    lista_fil = UT_KATALOG / "lista.txt"
    lista_fil.write_text(
        "\n".join(f"file '{f.resolve()}'" for f in filer),
        encoding="utf-8"
    )

    print(f"\nSlår ihop till {SLUTFIL.name}...")
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(lista_fil),
        "-c", "copy",
        str(SLUTFIL)
    ], capture_output=True)

    storlek = SLUTFIL.stat().st_size / (1024 * 1024)
    print(f"✓ Klar! {SLUTFIL.name} ({storlek:.1f} MB)")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=== Gugge-röstextraktorn ===\n")

    print("Läser SRT-filen...")
    srt_text  = SRT_FIL.read_text(encoding="utf-8")
    repliker  = parsa_srt(srt_text)
    rep_dict  = {r["nr"]: r for r in repliker}
    print(f"  {len(repliker)} repliker totalt.\n")

    gugge_nr = hitta_gugge_repliker(repliker)
    print(f"\nHittade {len(gugge_nr)} repliker som troligen är Gugges.\n")

    filer = klipp_ut(rep_dict, gugge_nr)
    sla_ihop(filer)

    print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Nästa steg — ElevenLabs röstkloning:

  1. Gå till elevenlabs.io → "Voices" → "Add Voice" → "Clone a voice"
  2. Ladda upp:  {SLUTFIL.name}
  3. Ge rösten ett namn, t.ex. "Gugge"
  4. Kopiera Voice ID och lägg i thor.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")


if __name__ == "__main__":
    main()
