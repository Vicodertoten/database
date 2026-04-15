from database_core.security import redact_database_url


def test_redact_database_url_masks_password_and_preserves_location() -> None:
    raw = "postgresql://postgres:s3cr3t@db.example.com:5432/postgres?sslmode=require"
    redacted = redact_database_url(raw)
    assert redacted == "postgresql://postgres:***@db.example.com:5432/postgres?sslmode=require"


def test_redact_database_url_returns_input_when_no_user_password_segment() -> None:
    raw = "postgresql://db.example.com:5432/postgres"
    assert redact_database_url(raw) == raw


def test_redact_database_url_handles_percent_encoded_password() -> None:
    raw = "postgresql://user:p%40ssw%3Ard@localhost:5432/dbname"
    redacted = redact_database_url(raw)
    assert redacted == "postgresql://user:***@localhost:5432/dbname"
