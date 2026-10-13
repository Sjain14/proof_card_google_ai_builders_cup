"""Data access layer. Routes talk to the Store protocol, never to Firestore directly.

Every write validates through a schemas.*Doc model first, so nothing malformed reaches
the database. The server writes with the Admin SDK (bypasses rules); clients only ever
read, and firestore.rules is deny by default.
"""

import secrets
from typing import Protocol

from app.schemas import CardDoc, ClaimDoc, SessionDoc


def new_id() -> str:
    return secrets.token_urlsafe(16)


class Store(Protocol):
    def create_session(self, doc: SessionDoc) -> str: ...
    def add_claim(self, session_id: str, doc: ClaimDoc) -> str: ...
    def get_card(self, card_id: str) -> CardDoc | None: ...
    def put_card(self, card_id: str, doc: CardDoc) -> None: ...


class InMemoryStore:
    def __init__(self) -> None:
        self.sessions: dict[str, SessionDoc] = {}
        self.claims: dict[str, dict[str, ClaimDoc]] = {}
        self.cards: dict[str, CardDoc] = {}

    def create_session(self, doc: SessionDoc) -> str:
        sid = new_id()
        self.sessions[sid] = doc
        self.claims[sid] = {}
        return sid

    def add_claim(self, session_id: str, doc: ClaimDoc) -> str:
        if session_id not in self.sessions:
            raise KeyError(session_id)
        cid = new_id()
        self.claims[session_id][cid] = doc
        return cid

    def get_card(self, card_id: str) -> CardDoc | None:
        return self.cards.get(card_id)

    def put_card(self, card_id: str, doc: CardDoc) -> None:
        self.cards[card_id] = doc


class FirestoreStore:  # pragma: no cover - exercised against the emulator / prod
    def __init__(self, project: str) -> None:
        from google.cloud import firestore

        self.db = firestore.Client(project=project or None)

    def create_session(self, doc: SessionDoc) -> str:
        sid = new_id()
        self.db.collection("sessions").document(sid).create(doc.model_dump(mode="json"))
        return sid

    def add_claim(self, session_id: str, doc: ClaimDoc) -> str:
        cid = new_id()
        ref = self.db.collection("sessions").document(session_id).collection("claims")
        ref.document(cid).create(doc.model_dump(mode="json"))
        return cid

    def get_card(self, card_id: str) -> CardDoc | None:
        snap = self.db.collection("cards").document(card_id).get()
        return CardDoc.model_validate(snap.to_dict()) if snap.exists else None

    def put_card(self, card_id: str, doc: CardDoc) -> None:
        # create() fails if the id exists: cards are immutable once issued.
        self.db.collection("cards").document(card_id).create(doc.model_dump(mode="json"))
