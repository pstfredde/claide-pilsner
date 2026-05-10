#!/usr/bin/env python3
"""
Webb-backend för pilsner-boten.
Kör: uvicorn app:app --reload
"""

import uuid
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Importera chattlogiken från thor.py
from thor import chat, STATISK_PROMPT, _KARAKTÄR

app = FastAPI()

# Sessioner sparas i minne (nollställs vid omstart)
_sessioner: dict[str, list] = {}


class ChatBegäran(BaseModel):
    meddelande: str
    session_id: str = ""


class ChatSvar(BaseModel):
    svar: str
    session_id: str


@app.post("/api/chat", response_model=ChatSvar)
def chatta(begäran: ChatBegäran) -> ChatSvar:
    # Skapa ny session om ingen finns
    sid = begäran.session_id or str(uuid.uuid4())
    if sid not in _sessioner:
        _sessioner[sid] = []

    messages = _sessioner[sid]
    messages.append({"role": "user", "content": begäran.meddelande})

    svar = chat(messages, begäran.meddelande)
    messages.append({"role": "assistant", "content": svar})

    return ChatSvar(svar=svar, session_id=sid)


@app.get("/api/karaktär")
def karaktär():
    return {"karaktär": _KARAKTÄR}


# Servera frontend
app.mount("/", StaticFiles(directory="static", html=True), name="static")
