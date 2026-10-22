"""Connections come from Airflow-style URIs in the environment (never from code)."""

from __future__ import annotations

import os
from urllib.parse import unquote, urlparse

import pymysql


def mysql_from_env(var: str) -> pymysql.connections.Connection:
    uri = os.environ.get(var)
    if not uri:
        raise RuntimeError(f"{var} is not set")
    u = urlparse(uri)
    return pymysql.connect(
        host=u.hostname,
        port=u.port or 3306,
        user=unquote(u.username or ""),
        password=unquote(u.password or ""),
        database=u.path.lstrip("/"),
        charset="utf8mb4",
        autocommit=False,
        connect_timeout=10,
        cursorclass=pymysql.cursors.DictCursor,
    )


def pg_dsn_from_env(var: str) -> str:
    uri = os.environ.get(var)
    if not uri:
        raise RuntimeError(f"{var} is not set")
    return uri.replace("postgres://", "postgresql://", 1)
