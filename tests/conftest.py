from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from uuid import uuid4

import psycopg
import pytest
from dotenv import load_dotenv
from psycopg import sql

_DEFAULT_TEST_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:5432/postgres"
load_dotenv(dotenv_path=Path(".env"))


def _base_database_url() -> str:
    return (
        os.environ.get("TEST_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or _DEFAULT_TEST_DATABASE_URL
    )


def _with_search_path(database_url: str, *, schema_name: str) -> str:
    parsed = urlparse(database_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    search_path_option = f"-csearch_path={schema_name},public"
    existing_options = query.get("options")
    if existing_options:
        query["options"] = f"{existing_options} {search_path_option}"
    else:
        query["options"] = search_path_option
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


@pytest.fixture
def database_url_factory() -> Callable[[], str]:
    base_url = _base_database_url()
    schema_names: list[str] = []

    def _create() -> str:
        schema_name = f"test_{uuid4().hex}"
        with psycopg.connect(base_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema_name))
            )
        schema_names.append(schema_name)
        return _with_search_path(base_url, schema_name=schema_name)

    try:
        yield _create
    finally:
        with psycopg.connect(base_url, autocommit=True) as connection:
            for schema_name in schema_names:
                connection.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema_name))
                )


@pytest.fixture
def database_url(database_url_factory: Callable[[], str]) -> str:
    return database_url_factory()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        fixture_names = set(getattr(item, "fixturenames", []))
        if {"database_url", "database_url_factory"} & fixture_names:
            item.add_marker("integration_db")
