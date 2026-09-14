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
from langflow.services.database.models.folder.model import Folder
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


async def _home_folder_id(session, user_id: UUID):
    """The project Studio opens on for this member, if there is one.

    `_initialize_jit_user_defaults` calls `get_or_create_default_folder` just
    before it calls this seeder, so by the time we run there is one. Picking the
    oldest rather than asserting a name keeps this working for a member who has
    since renamed it, and returning None on a member who somehow has no folder
    leaves the old behaviour rather than failing their sign-in.
    """
    folders = (await session.exec(select(Folder).where(Folder.user_id == user_id))).all()
    if not folders:
        return None
    return sorted(folders, key=lambda f: (f.id is None, str(f.id)))[0].id


async def seed_member_routines(session, user_id: UUID) -> int:
    """Give ``user_id`` the box's routines. Returns how many were written.

    The canonical set is what a **superuser** owns, not everything wearing the
    tag: the copies carry the tag too, so "everything tagged" would make the
    second member inherit the first member's copies on top of the box's. That is
    not a cosmetic duplicate — ``flow`` is unique on (user_id, name), so the
    second sign-in would raise IntegrityError and fail outright.

    The copies go into the member's own project. Studio lists flows by folder
    and opens on the default one, so a copy with no ``folder_id`` is a row in
    the database that the member never sees — which is how this shipped: four
    correct routines, invisible, under a canvas that said "Start building".
    """
    home = await _home_folder_id(session, user_id)
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
                    folder_id=home,
                )
            )
            written += 1
        elif _untouched(copy):
            copy.data = deepcopy(source.data)
            copy.tags = [ROUTINE_TAG, _seed_tag(source.data)]
            # Also repairs a copy seeded before this had a folder at all: an
            # existing box has members whose routines are already orphaned, and
            # their next sign-in is the only chance to put them somewhere
            # visible. A copy the member has moved is left where they put it.
            if copy.folder_id is None:
                copy.folder_id = home
            session.add(copy)
            written += 1

    await session.commit()
    return written
