"""Data access layer. Routes and the pipeline talk to the Store protocol, never to Firestore.

Every write validates through a schemas.*Doc model first, so nothing malformed reaches
the database. The server writes with the Admin SDK (bypasses rules); clients only ever
read, and firestore.rules is deny by default.

Updates go through _apply(): the current doc + the change set is re-validated as a whole
model before anything is written, so a partial update can never break the schema.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from threading import Lock
from typing import Any, Protocol

from pydantic import BaseModel

from app.schemas import CardDoc, CheckDoc, ClaimDoc, FactBankDoc, SessionDoc


def new_id() -> str:
    return secrets.token_urlsafe(16)


def new_card_id() -> str:
    # 12 url safe chars = 72 bits: short enough for a QR code, too large to guess.
    return secrets.token_urlsafe(9)


def _apply[M: BaseModel](doc: M, changes: dict[str, Any]) -> M:
    return type(doc).model_validate({**doc.model_dump(), **changes})


class Store(Protocol):
    def create_session(self, doc: SessionDoc) -> str: ...
    def count_sessions_since(self, owner_uid: str, day: str) -> int: ...
    def count_anon_sessions_today(self, day: str) -> int: ...
    def get_session(self, session_id: str) -> SessionDoc | None: ...
    def update_session(self, session_id: str, **changes: Any) -> None: ...
    def add_claim(self, session_id: str, doc: ClaimDoc) -> str: ...
    def get_claim(self, session_id: str, claim_id: str) -> ClaimDoc | None: ...
    def list_claims(self, session_id: str) -> list[tuple[str, ClaimDoc]]: ...
    def update_claim(self, session_id: str, claim_id: str, **changes: Any) -> None: ...
    def get_card(self, card_id: str) -> CardDoc | None: ...
    def put_card(self, card_id: str, doc: CardDoc) -> None: ...
    def add_check(self, doc: CheckDoc) -> None: ...
    def get_fact_bank(self, key: str) -> FactBankDoc | None: ...
    def put_fact_bank(self, doc: FactBankDoc) -> None: ...
    def get_claim_card(self, key: str) -> tuple[str, datetime] | None: ...
    def put_claim_card(self, key: str, card_id: str) -> None: ...


class InMemoryStore:
    def __init__(self) -> None:
        self.sessions: dict[str, SessionDoc] = {}
        self.claims: dict[str, dict[str, ClaimDoc]] = {}
        self.cards: dict[str, CardDoc] = {}
        self.checks: list[CheckDoc] = []
        self.fact_banks: dict[str, FactBankDoc] = {}
        self.claim_cards: dict[str, tuple[str, datetime]] = {}
        self._lock = Lock()

    def create_session(self, doc: SessionDoc) -> str:
        sid = new_id()
        with self._lock:
            self.sessions[sid] = doc
            self.claims[sid] = {}
        return sid

    def count_sessions_since(self, owner_uid: str, day: str) -> int:
        return sum(
            1
            for d in self.sessions.values()
            if d.owner_uid == owner_uid and d.created_at.date().isoformat() >= day
        )

    def count_anon_sessions_today(self, day: str) -> int:
        with self._lock:
            return sum(
                1
                for d in self.sessions.values()
                if d.is_anonymous and d.created_at.date().isoformat() >= day
            )

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
        changes = {**changes, "updated_at": datetime.now(UTC)}
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

    def add_check(self, doc: CheckDoc) -> None:
        with self._lock:
            self.checks.append(doc)

    def get_fact_bank(self, key: str) -> FactBankDoc | None:
        return self.fact_banks.get(key)

    def put_fact_bank(self, doc: FactBankDoc) -> None:
        with self._lock:
            self.fact_banks[doc.key] = doc

    def get_claim_card(self, key: str) -> tuple[str, datetime] | None:
        return self.claim_cards.get(key)

    def put_claim_card(self, key: str, card_id: str) -> None:
        with self._lock:
            self.claim_cards[key] = (card_id, datetime.now(UTC))


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
        if doc.is_anonymous:
            from google.cloud import firestore

            day = doc.created_at.date().isoformat()
            self.db.collection("daily_stats").document(day).set(
                {"anon_sessions": firestore.Increment(1)},
                merge=True,
            )
        return sid

    def count_anon_sessions_today(self, day: str) -> int:
        snap = self.db.collection("daily_stats").document(day).get()
        if not snap.exists:
            return 0
        data = snap.to_dict() or {}
        return int(data.get("anon_sessions", 0))

    def count_sessions_since(self, owner_uid: str, day: str) -> int:
        """Server side count (one aggregation read). created_at is stored as an ISO 8601
        string, so ">= 'YYYY-MM-DD'" is an exact day bound. Uses the existing
        (owner_uid, created_at desc) index. Docs:
        https://firebase.google.com/docs/firestore/query-data/aggregation-queries"""
        from google.cloud.firestore_v1 import FieldFilter, Query

        q = (
            self.db.collection("sessions")
            .where(filter=FieldFilter("owner_uid", "==", owner_uid))
            .where(filter=FieldFilter("created_at", ">=", day))
            .order_by("created_at", direction=Query.DESCENDING)
        )
        # SDK annotations say count() returns a Type; at runtime get() is [[result]].
        agg: Any = q.count(alias="n")
        return int(agg.get()[0][0].value)

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
        changes = {**changes, "updated_at": datetime.now(UTC)}
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

    def add_check(self, doc: CheckDoc) -> None:
        self.db.collection("checks").document(new_id()).create(doc.model_dump(mode="json"))

    def get_fact_bank(self, key: str) -> FactBankDoc | None:
        snap = self.db.collection("fact_banks").document(key).get()
        return FactBankDoc.model_validate(snap.to_dict()) if snap.exists else None

    def put_fact_bank(self, doc: FactBankDoc) -> None:
        # set(), not create(): a stale bank is replaced by a fresh one under the same key.
        self.db.collection("fact_banks").document(doc.key).set(doc.model_dump(mode="json"))

    def get_claim_card(self, key: str) -> tuple[str, datetime] | None:
        snap = self.db.collection("claim_cards").document(key).get()
        if not snap.exists:
            return None
        d = snap.to_dict() or {}
        at = d.get("at")
        if not isinstance(d.get("card_id"), str) or not isinstance(at, datetime):
            return None
        return d["card_id"], at

    def put_claim_card(self, key: str, card_id: str) -> None:
        self.db.collection("claim_cards").document(key).set(
            {"card_id": card_id, "at": datetime.now(UTC)}
        )
