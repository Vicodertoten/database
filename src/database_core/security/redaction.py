from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


def redact_database_url(database_url: str) -> str:
    parsed = urlsplit(database_url)
    if "@" not in parsed.netloc:
        return database_url
    user_info, host_info = parsed.netloc.rsplit("@", 1)
    if ":" not in user_info:
        return database_url
    username, _password = user_info.split(":", 1)
    safe_netloc = f"{username}:***@{host_info}"
    return urlunsplit((parsed.scheme, safe_netloc, parsed.path, parsed.query, parsed.fragment))
