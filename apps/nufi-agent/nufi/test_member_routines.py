"""The box's department routines, and the member who signs in over SSO.

P2 shipped four routines that read the department drives. They are created by
`build_flows.py --box` under the box's superuser, and a member arriving through
`/enter/studio` becomes a JIT non-superuser account that owns nothing — so the
feature the box is sold on lists zero flows for everyone but the admin.
"""

from uuid import uuid4

import pytest
from langflow.services.database.models.flow.model import Flow
from langflow.services.database.models.user.model import User
from nufi.member_routines import ROUTINE_TAG, seed_member_routines
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession


# This file lives in nufi/, outside the vendored tree, so it cannot use
# src/backend/tests/conftest.py. The fixture below is that conftest's
# async_session, kept here deliberately: the alternative is a test inside
# upstream's tree, which is the divergence this whole arrangement avoids.
@pytest.fixture
async def async_session():
    engine = create_async_engine(
        "sqlite+aiosqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    try:
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.drop_all)
    finally:
        await engine.dispose()

NAMES = ("docqa", "meeting", "helpdesk", "weekly")


async def _user(session, username, *, superuser=False):
    user = User(username=username, password="x", is_active=True, is_superuser=superuser)
    session.add(user)
    await session.commit()
    return user


async def _canonical_routines(session, owner_id, *, body="v1"):
    for name in NAMES:
        session.add(
            Flow(
                name=name,
                description=f"the {name} routine",
                user_id=owner_id,
                tags=[ROUTINE_TAG],
                data={"nodes": [{"id": "chat-input", "body": body}], "edges": []},
            )
        )
    await session.commit()


async def _flows_of(session, user_id):
    return (await session.exec(select(Flow).where(Flow.user_id == user_id))).all()


async def test_a_member_gets_a_copy_of_every_box_routine(async_session):
    owner = await _user(async_session, "box-admin", superuser=True)
    member = await _user(async_session, "alice")
    await _canonical_routines(async_session, owner.id)

    await seed_member_routines(async_session, member.id)

    mine = await _flows_of(async_session, member.id)
    assert sorted(f.name for f in mine) == sorted(NAMES), "the member should own one copy of each routine"
    assert all(f.id != uuid4() for f in mine)


async def test_a_second_member_copies_the_box_not_the_first_member(async_session):
    # The copies carry the routine tag too, so "everything tagged" is not the
    # canonical set: the second member to sign in would inherit the first
    # member's copies on top of the box's, and the third would inherit both.
    owner = await _user(async_session, "box-admin", superuser=True)
    alice = await _user(async_session, "alice")
    bob = await _user(async_session, "bob")
    await _canonical_routines(async_session, owner.id)

    await seed_member_routines(async_session, alice.id)
    await seed_member_routines(async_session, bob.id)

    assert len(await _flows_of(async_session, bob.id)) == len(NAMES)


async def test_signing_in_again_does_not_duplicate_the_routines(async_session):
    # This runs on every JIT sign-in, not only the first.
    owner = await _user(async_session, "box-admin", superuser=True)
    alice = await _user(async_session, "alice")
    await _canonical_routines(async_session, owner.id)

    await seed_member_routines(async_session, alice.id)
    await seed_member_routines(async_session, alice.id)
    await seed_member_routines(async_session, alice.id)

    assert len(await _flows_of(async_session, alice.id)) == len(NAMES)


async def _box_ships_a_new_version(session, owner_id, body):
    for flow in await _flows_of(session, owner_id):
        flow.data = {"nodes": [{"id": "chat-input", "body": body}], "edges": []}
        session.add(flow)
    await session.commit()


def _body(flow):
    return flow.data["nodes"][0]["body"]


async def test_a_copy_the_member_never_touched_follows_the_box(async_session):
    owner = await _user(async_session, "box-admin", superuser=True)
    alice = await _user(async_session, "alice")
    await _canonical_routines(async_session, owner.id, body="v1")
    await seed_member_routines(async_session, alice.id)

    await _box_ships_a_new_version(async_session, owner.id, "v2")
    await seed_member_routines(async_session, alice.id)

    mine = await _flows_of(async_session, alice.id)
    assert [_body(f) for f in mine] == ["v2"] * len(NAMES)


async def test_a_copy_the_member_edited_is_never_overwritten(async_session):
    # The one thing this must never do is destroy a member's work. Verified
    # against an implementation with the _untouched() guard removed: without it
    # this test fails on alice's own wording being replaced by the box's.
    owner = await _user(async_session, "box-admin", superuser=True)
    alice = await _user(async_session, "alice")
    await _canonical_routines(async_session, owner.id, body="v1")
    await seed_member_routines(async_session, alice.id)

    weekly = next(f for f in await _flows_of(async_session, alice.id) if f.name == "weekly")
    weekly.data = {"nodes": [{"id": "chat-input", "body": "alice's own wording"}], "edges": []}
    async_session.add(weekly)
    await async_session.commit()

    await _box_ships_a_new_version(async_session, owner.id, "v2")
    await seed_member_routines(async_session, alice.id)

    mine = {f.name: f for f in await _flows_of(async_session, alice.id)}
    assert _body(mine["weekly"]) == "alice's own wording", "an edited routine must survive the box's update"
    assert [_body(mine[n]) for n in NAMES if n != "weekly"] == ["v2"] * (len(NAMES) - 1), (
        "the ones she never touched should still follow the box"
    )


async def test_the_jit_sign_in_path_seeds_the_routines(async_session, monkeypatch):
    # The seeder is only worth anything if the SSO path calls it. Everything else
    # in this file tests the seeder in isolation; this pins the wiring. The auth
    # service imports its helpers inside the function body, as the surrounding
    # code does, so the patch goes on the defining module.
    import nufi.member_routines as member_routines
    from langflow.services.auth.service import AuthService

    called: list = []

    async def _spy(session, user_id):
        called.append(user_id)
        return 0

    monkeypatch.setattr(member_routines, "seed_member_routines", _spy)

    member = await _user(async_session, "alice")
    await AuthService._initialize_jit_user_defaults(member, async_session)

    assert called == [member.id], "the JIT sign-in path must seed the member's routines"
