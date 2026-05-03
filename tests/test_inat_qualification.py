from urllib.error import HTTPError

from database_core.adapters.inaturalist_qualification import PacingRetryQualifier
from database_core.domain.enums import MediaType, SourceName
from database_core.domain.models import AIQualification, MediaAsset
from database_core.qualification.ai import GeminiRequestError


class FakeClock:
    def __init__(self) -> None:
        self.current = 0.0
        self.sleep_calls: list[float] = []

    def now(self) -> float:
        return self.current

    def sleep(self, delay_seconds: float) -> None:
        self.sleep_calls.append(delay_seconds)
        self.current += delay_seconds


class RetryingQualifier:
    def __init__(self, failures_before_success: int) -> None:
        self.failures_remaining = failures_before_success
        self.calls = 0

    def qualify(
        self,
        media_asset,
        *,
        image_bytes: bytes | None = None,
        bird_image_review_input=None,
    ):
        del media_asset, image_bytes, bird_image_review_input
        self.calls += 1
        if self.failures_remaining > 0:
            self.failures_remaining -= 1
            raise HTTPError(
                url="https://generativelanguage.googleapis.com/v1beta/models/test:generateContent",
                code=429,
                msg="Too Many Requests",
                hdrs={"Retry-After": "2.5"},
                fp=None,
            )
        return AIQualification(
            technical_quality="high",
            pedagogical_quality="medium",
            life_stage="unknown",
            sex="unknown",
            visible_parts=["full_body", "head", "beak"],
            view_angle="lateral",
            confidence=0.95,
            model_name="gemini-3.1-flash-lite-preview",
        )


class SuccessfulQualifier:
    def __init__(self) -> None:
        self.calls = 0

    def qualify(
        self,
        media_asset,
        *,
        image_bytes: bytes | None = None,
        bird_image_review_input=None,
    ):
        del media_asset, image_bytes, bird_image_review_input
        self.calls += 1
        return AIQualification(
            technical_quality="high",
            pedagogical_quality="medium",
            life_stage="unknown",
            sex="unknown",
            visible_parts=["full_body", "head", "beak"],
            view_angle="lateral",
            confidence=0.95,
            model_name="gemini-3.1-flash-lite-preview",
        )


class WrappedRetryingQualifier:
    def __init__(self, failures_before_success: int) -> None:
        self.failures_remaining = failures_before_success
        self.calls = 0

    def qualify(
        self,
        media_asset,
        *,
        image_bytes: bytes | None = None,
        bird_image_review_input=None,
    ):
        del media_asset, image_bytes, bird_image_review_input
        self.calls += 1
        if self.failures_remaining > 0:
            self.failures_remaining -= 1
            raise GeminiRequestError(
                "Gemini API request failed with HTTP 429: Too Many Requests",
                status_code=429,
                retry_after_seconds=2.0,
                retryable=True,
            )
        return AIQualification(
            technical_quality="high",
            pedagogical_quality="medium",
            life_stage="unknown",
            sex="unknown",
            visible_parts=["full_body", "head", "beak"],
            view_angle="lateral",
            confidence=0.95,
            model_name="gemini-3.1-flash-lite-preview",
        )


def test_pacing_retry_qualifier_retries_http_429_then_succeeds() -> None:
    clock = FakeClock()
    base_qualifier = RetryingQualifier(failures_before_success=2)
    qualifier = PacingRetryQualifier(
        base_qualifier=base_qualifier,
        request_interval_seconds=0.0,
        max_retries=3,
        initial_backoff_seconds=1.0,
        max_backoff_seconds=10.0,
        sleep_func=clock.sleep,
        clock_func=clock.now,
    )

    qualification = qualifier.qualify(_media_asset(), image_bytes=b"image")

    assert qualification is not None
    assert base_qualifier.calls == 3
    assert clock.sleep_calls == [2.5, 2.5]


def test_pacing_retry_qualifier_enforces_min_interval_between_requests() -> None:
    clock = FakeClock()
    base_qualifier = SuccessfulQualifier()
    qualifier = PacingRetryQualifier(
        base_qualifier=base_qualifier,
        request_interval_seconds=0.5,
        max_retries=0,
        initial_backoff_seconds=1.0,
        max_backoff_seconds=10.0,
        sleep_func=clock.sleep,
        clock_func=clock.now,
    )

    qualifier.qualify(_media_asset(), image_bytes=b"image")
    qualifier.qualify(_media_asset(), image_bytes=b"image")

    assert base_qualifier.calls == 2
    assert clock.sleep_calls == [0.5]


def test_pacing_retry_qualifier_retries_wrapped_gemini_errors() -> None:
    clock = FakeClock()
    base_qualifier = WrappedRetryingQualifier(failures_before_success=1)
    qualifier = PacingRetryQualifier(
        base_qualifier=base_qualifier,
        request_interval_seconds=0.0,
        max_retries=2,
        initial_backoff_seconds=1.0,
        max_backoff_seconds=10.0,
        sleep_func=clock.sleep,
        clock_func=clock.now,
    )

    qualification = qualifier.qualify(_media_asset(), image_bytes=b"image")

    assert qualification is not None
    assert base_qualifier.calls == 2
    assert clock.sleep_calls == [2.0]


def _media_asset() -> MediaAsset:
    return MediaAsset(
        media_id="media:fixture:retry",
        source_name=SourceName.INATURALIST,
        source_media_id="fixture-retry",
        media_type=MediaType.IMAGE,
        source_url="fixture://media/retry",
        attribution="fixture",
        author="observer",
        license="CC-BY",
        mime_type="image/jpeg",
        file_extension="jpg",
        width=1600,
        height=1200,
        source_observation_uid="obs:fixture:retry",
        canonical_taxon_id="taxon:birds:000014",
        raw_payload_ref="fixture.json#/media/retry",
    )
