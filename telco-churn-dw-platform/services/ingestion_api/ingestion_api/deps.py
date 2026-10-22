from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings


def get_factory(request: Request) -> sessionmaker[Session]:
    return request.app.state.session_factory  # type: ignore[no-any-return]


def get_session(factory: Annotated[sessionmaker[Session], Depends(get_factory)]) -> Iterator[Session]:
    with factory() as session:
        yield session


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def wake_relay(request: Request) -> None:
    relay = getattr(request.app.state, "relay", None)
    if relay is not None:
        relay.wake()


SessionDep = Annotated[Session, Depends(get_session)]
FactoryDep = Annotated[sessionmaker[Session], Depends(get_factory)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
