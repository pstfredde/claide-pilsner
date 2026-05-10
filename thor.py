#!/usr/bin/env python3
"""
Pilsner-boten — en AI-kompis i pilsnerfilmernas anda.
Kör: python thor.py
Kör i debuggläge: python thor.py --debug
Avsluta: skriv 'sluta', 'hej då' eller tryck Ctrl+C

Aktiv karaktär styrs av config.toml → [bot] karaktär
"""

import json
import pathlib
import sys
import tomllib
import anthropic
from rag import hitta_relevant_slang
from verktyg import VERKTYG, kör_verktyg

DEBUG = "--debug" in sys.argv

# ── Läs config ────────────────────────────────────────────────────────────────

_ROT      = pathlib.Path(__file__).parent
_cfg      = tomllib.loads((_ROT / "config.toml").read_text(encoding="utf-8"))

_CLAUDE_MODELL         = _cfg["claude"]["modell"]
_MAX_TOKENS            = _cfg["claude"]["max_tokens"]
_KARAKTÄR              = _cfg["bot"]["karakter"]
_ANTAL_EXEMPELREPLIKER = _cfg["bot"]["antal_exempelrepliker"]

_KAR_PATH = _ROT / "lexicon" / _KARAKTÄR


# ── Debugg-utskrift ───────────────────────────────────────────────────────────

def debugg(rubrik: str, innehall: str = "") -> None:
    if not DEBUG:
        return
    print(f"\n\033[90m┌─ 🔍 {rubrik}")
    if innehall:
        for rad in innehall.splitlines():
            print(f"\033[90m│  {rad}")
    print(f"\033[90m└{'─' * 50}\033[0m")


# ── Ladda karaktär ────────────────────────────────────────────────────────────

def _ladda_karaktär() -> str:
    """
    Bygger systempromten för aktiv karaktär.
    Läser prompt.txt och infogar exempelrepliker från lexikon.json.
    """
    prompt_fil = _KAR_PATH / "prompt.txt"
    lex_fil    = _KAR_PATH / "lexikon.json"

    bas_prompt = prompt_fil.read_text(encoding="utf-8").strip()

    lexikon   = json.loads(lex_fil.read_text(encoding="utf-8"))
    repliker  = "\n".join(
        f'  - "{r}"'
        for r in (lexikon.get("exempelrepliker") or [])[:_ANTAL_EXEMPELREPLIKER]
    )

    if repliker:
        return bas_prompt + f"\n\nEXEMPELREPLIKER FRÅN FILMEN — tala precis såhär:\n{repliker}"
    return bas_prompt


STATISK_PROMPT = _ladda_karaktär()
debugg(f"Karaktär laddad: {_KARAKTÄR}", f"Prompt: {len(STATISK_PROMPT)} tecken")


# ── Claude-klient ─────────────────────────────────────────────────────────────

client = anthropic.Anthropic()


# ── Chattfunktioner ───────────────────────────────────────────────────────────

def bygg_slang_block(fråga: str) -> tuple[str, dict]:
    """Hämtar relevant slang via RAG och formaterar som textblock."""
    slang = hitta_relevant_slang(fråga)
    rader = "\n".join(f'  "{k}": {v}' for k, v in slang.items())
    return f"RELEVANT SLANG FÖR DETTA SVAR (använd gärna dessa ord):\n{rader}", slang


def chat(messages: list, senaste_fråga: str) -> str:
    """
    Skickar till Claude med två systemprompt-block:
      1. Statisk personlighet  → cachas
      2. Dynamiskt slang       → hämtas via RAG, ej cachat

    Hanterar tool use automatiskt i en loop tills Claude ger ett textsvar.
    """
    slang_block, slang_dict = bygg_slang_block(senaste_fråga)

    debugg("RAG — hämtade slangord",
           "\n".join(f"{k}: {v}" for k, v in slang_dict.items()))
    debugg("Konversationshistorik",
           f"{len(messages)} meddelanden")

    system = [
        {
            "type": "text",
            "text": STATISK_PROMPT,
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": slang_block,
        },
    ]

    # Tool use-loop — Claude kan anropa verktyg flera gånger innan den svarar
    aktuella_messages = messages.copy()
    while True:
        response = client.messages.create(
            model=_CLAUDE_MODELL,
            max_tokens=_MAX_TOKENS,
            system=system,
            tools=VERKTYG,
            messages=aktuella_messages,
        )

        usage = response.usage
        debugg("Token-användning",
               f"Input:       {usage.input_tokens} tokens\n"
               f"Output:      {usage.output_tokens} tokens\n"
               f"Cache write: {getattr(usage, 'cache_creation_input_tokens', 0)} tokens\n"
               f"Cache read:  {getattr(usage, 'cache_read_input_tokens', 0)} tokens\n"
               f"Stop reason: {response.stop_reason}")

        # Inget verktygsanrop — returnera svaret direkt
        if response.stop_reason != "tool_use":
            return next(b.text for b in response.content if b.type == "text")

        # Hantera verktygsanrop
        verktygs_anrop = [b for b in response.content if b.type == "tool_use"]
        debugg("Verktygsanrop",
               "\n".join(f"{v.name}({v.input})" for v in verktygs_anrop))

        # Lägg till Claudes svar (med tool_use-block) i historiken
        aktuella_messages.append({"role": "assistant", "content": response.content})

        # Kör verktygen och skicka tillbaka resultaten
        resultat = []
        for anrop in verktygs_anrop:
            svar = kör_verktyg(anrop.name, anrop.input)
            debugg(f"Verktygsresultat: {anrop.name}", svar)
            resultat.append({
                "type": "tool_result",
                "tool_use_id": anrop.id,
                "content": svar,
            })

        aktuella_messages.append({"role": "user", "content": resultat})


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    namn = _KARAKTÄR.capitalize()
    print("=" * 55)
    print(f"  {namn} — Pilsnerfilmsboten")
    print("=" * 55)
    print("  Skriv 'hej då' eller 'sluta' för att avsluta.")
    print("=" * 55)
    print()

    messages = []
    öppning_fråga = "Hälsa och presentera dig kort!"

    opening = chat(
        [{"role": "user", "content": öppning_fråga}],
        öppning_fråga
    )
    print(f"{namn}: {opening}\n")
    messages.append({"role": "user",      "content": öppning_fråga})
    messages.append({"role": "assistant", "content": opening})

    while True:
        try:
            user_input = input("Du:    ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{namn}: Herre gud, du försvann rakt av! Tjing!")
            break

        if not user_input:
            continue

        if user_input.lower() in {"sluta", "hej då", "hejdå", "bye", "quit", "exit", "q"}:
            farewell = chat(
                messages + [{"role": "user", "content": "Hejdå!"}],
                "hejdå adjö"
            )
            print(f"\n{namn}: {farewell}")
            break

        messages.append({"role": "user", "content": user_input})

        try:
            reply = chat(messages, user_input)
            messages.append({"role": "assistant", "content": reply})
            print(f"\n{namn}: {reply}\n")
        except anthropic.APIError as e:
            print(f"\n[FEL: {e}]\n")
            messages.pop()


if __name__ == "__main__":
    main()
