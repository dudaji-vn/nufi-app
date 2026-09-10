"""The box's department routines, seeded into a member's own space.

`build_flows.py --box` creates the routines under the box's superuser. A member
who arrives through `/enter/studio` becomes a JIT non-superuser account, and a
flow is visible to the account that owns it, so without this the routines are an
admin-only feature.

Each member gets their own copies, so a member can adapt `weekly` to their
department. The cost of copies is drift, and the fingerprint below is what keeps
it bounded: a copy nobody has touched still hashes to the value stored on it when
it was seeded, and is refreshed from the box; a copy the member edited does not,
and is left alone for good.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from uuid import UUID

from langflow.services.database.models.flow.model import Flow
from langflow.services.database.models.user.model import User
from sqlmodel import select

ROUTINE_TAG = "nufi-routine"
SEED_TAG_PREFIX = "nufi-seed:"


def _fingerprint(data) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()[:12]


def _seed_tag(data) -> str:
    return f"{SEED_TAG_PREFIX}{_fingerprint(data)}"


def _seeded_as(flow: Flow) -> str | None:
    """The fingerprint this copy carried when it was last seeded, if any."""
    for tag in flow.tags or []:
        if tag.startswith(SEED_TAG_PREFIX):
            return tag[len(SEED_TAG_PREFIX) :]
    return None


def _untouched(flow: Flow) -> bool:
    seeded = _seeded_as(flow)
    return seeded is not None and seeded == _fingerprint(flow.data)


async def seed_member_routines(session, user_id: UUID) -> int:
    """Give ``user_id`` the box's routines. Returns how many were written.

    The canonical set is what a **superuser** owns, not everything wearing the
    tag: the copies carry the tag too, so "everything tagged" would make the
    second member inherit the first member's copies on top of the box's. That is
    not a cosmetic duplicate — ``flow`` is unique on (user_id, name), so the
    second sign-in would raise IntegrityError and fail outright.
    """
    stmt = select(Flow).join(User, User.id == Flow.user_id).where(User.is_superuser == True)  # noqa: E712
    rows = (await session.exec(stmt)).all()
    canonical = [f for f in rows if f.tags and ROUTINE_TAG in f.tags and f.user_id != user_id]

    # This runs on every JIT sign-in, not only the first.
    mine = {f.name: f for f in (await session.exec(select(Flow).where(Flow.user_id == user_id))).all()}

    written = 0
    for source in canonical:
        copy = mine.get(source.name)
        if copy is None:
            session.add(
                Flow(
                    name=source.name,
                    description=source.description,
                    icon=source.icon,
                    tags=[ROUTINE_TAG, _seed_tag(source.data)],
                    data=deepcopy(source.data),
                    user_id=user_id,
                )
            )
            written += 1
        elif _untouched(copy):
            copy.data = deepcopy(source.data)
            copy.tags = [ROUTINE_TAG, _seed_tag(source.data)]
            session.add(copy)
            written += 1

    await session.commit()
    return written
