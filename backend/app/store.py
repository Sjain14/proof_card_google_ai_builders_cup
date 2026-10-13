"""Data access layer. Routes and the pipeline talk to the Store protocol, never to Firestore.

Every write validates through a schemas.*Doc model first, so nothing malformed reaches
the database. The server writes with the Admin SDK (bypasses rules); clients only ever
read, and firestore.rules is deny by default.

Updates go through _apply(): the current doc + the change set is re-validated as a whole
model before anything is written, so a partial update can never break the schema.
"""

from __future__ import annotations

import secrets
from threading import Lock
from typing import Any, Protocol

from pydantic import BaseModel

from app.schemas import CardDoc, ClaimDoc, SessionDoc


def new_id() -> str:
    return secrets.token_urlsafe(16)


def new_card_id() -> str:
    # 12 url safe chars = 72 bits: short enough for a QR code, too large to guess.
    return secrets.token_urlsafe(9)


def _apply[M: BaseModel](doc: M, changes: dict[str, Any]) -> M:
    return type(doc).model_validate({**doc.model_dump(), **changes})


class Store(Protocol):
    def create_session(self, doc: SessionDoc) -> str: ...
    def get_session(self, session_id: str) -> SessionDoc | None: ...
    def update_session(self, session_id: str, **changes: Any) -> None: ...
    def add_claim(self, session_id: str, doc: ClaimDoc) -> str: ...
    def get_claim(self, session_id: str, claim_id: str) -> ClaimDoc | None: ...
    def list_claims(self, session_id: str) -> list[tuple[str, ClaimDoc]]: ...
    def update_claim(self, session_id: str, claim_id: str, **changes: Any) -> None: ...
    def get_card(self, card_id: str) -> CardDoc | None: ...
    def put_card(self, card_id: str, doc: CardDoc) -> None: ...


class InMemoryStore:
    def __init__(self) -> None:
        self.sessions: dict[str, SessionDoc] = {}
        self.claims: dict[str, dict[str, ClaimDoc]] = {}
        self.cards: dict[str, CardDoc] = {}
        self._lock = Lock()

    def create_session(self, doc: SessionDoc) -> str:
        sid = new_id()
        with self._lock:
            self.sessions[sid] = doc
            self.claims[sid] = {}
        return sid

    def get_session(self, session_id: str) -> SessionDoc | None:
        return self.sessions.get(session_id)

    def update_session(self, session_id: str, **changes: Any) -> None:
        with self._lock:
            self.sessions[session_id] = _apply(self.sessions[session_id], changes)

    def add_claim(self, session_id: str, doc: ClaimDoc) -> str:
        if session_id not in self.sessions:
            raise KeyError(session_id)
        cid = new_id()
        with self._lock:
            self.claims[session_id][cid] = doc
        return cid

    def get_claim(self, session_id: str, claim_id: str) -> ClaimDoc | None:
        return self.claims.get(session_id, {}).get(claim_id)

    def list_claims(self, session_id: str) -> list[tuple[str, ClaimDoc]]:
        items = list(self.claims.get(session_id, {}).items())
        return sorted(items, key=lambda kv: kv[1].created_at)

    def update_claim(self, session_id: str, claim_id: str, **changes: Any) -> None:
        with self._lock:
            cur = self.claims[session_id][claim_id]
            self.claims[session_id][claim_id] = _apply(cur, changes)

    def get_card(self, card_id: str) -> CardDoc | None:
        return self.cards.get(card_id)

    def put_card(self, card_id: str, doc: CardDoc) -> None:
        with self._lock:
            if card_id in self.cards:
                raise ValueError("card ids are immutable")
            self.cards[card_id] = doc


class FirestoreStore:  # pragma: no cover - exercised against the emulator / prod
    def __init__(self, project: str) -> None:
        from google.cloud import firestore

        self.db = firestore.Client(project=project or None)

    def _session(self, sid: str) -> Any:
        return self.db.collection("sessions").document(sid)

    def _claim(self, sid: str, cid: str) -> Any:
        return self._session(sid).collection("claims").document(cid)

    def create_session(self, doc: SessionDoc) -> str:
        sid = new_id()
        self._session(sid).create(doc.model_dump(mode="json"))
        return sid

    def get_session(self, session_id: str) -> SessionDoc | None:
        snap = self._session(session_id).get()
        return SessionDoc.model_validate(snap.to_dict()) if snap.exists else None

    def update_session(self, session_id: str, **changes: Any) -> None:
        cur = self.get_session(session_id)
        if cur is None:
            raise KeyError(session_id)
        new = _apply(cur, changes).model_dump(mode="json")
        self._session(session_id).update({k: new[k] for k in changes})

    def add_claim(self, session_id: str, doc: ClaimDoc) -> str:
        cid = new_id()
        self._claim(session_id, cid).create(doc.model_dump(mode="json"))
        return cid

    def get_claim(self, session_id: str, claim_id: str) -> ClaimDoc | None:
        snap = self._claim(session_id, claim_id).get()
        return ClaimDoc.model_validate(snap.to_dict()) if snap.exists else None

    def list_claims(self, session_id: str) -> list[tuple[str, ClaimDoc]]:
        q = self._session(session_id).collection("claims").order_by("created_at")
        return [(s.id, ClaimDoc.model_validate(s.to_dict())) for s in q.stream()]

    def update_claim(self, session_id: str, claim_id: str, **changes: Any) -> None:
        cur = self.get_claim(session_id, claim_id)
        if cur is None:
            raise KeyError(claim_id)
        new = _apply(cur, changes).model_dump(mode="json")
        self._claim(session_id, claim_id).update({k: new[k] for k in changes})

    def get_card(self, card_id: str) -> CardDoc | None:
        snap = self.db.collection("cards").document(card_id).get()
        return CardDoc.model_validate(snap.to_dict()) if snap.exists else None

    def put_card(self, card_id: str, doc: CardDoc) -> None:
        # create() fails if the id exists: cards are immutable once issued.
        self.db.collection("cards").document(card_id).create(doc.model_dump(mode="json"))
