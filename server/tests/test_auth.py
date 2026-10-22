"""Unit tests for admin authorization modes (civic.auth.authorize)."""

from civic.auth import authorize
from civic.settings import Settings


def make_settings(**overrides) -> Settings:
    base = dict(
        civic_environment="prod",
        admin_token="",
        oidc_issuer="",
        oidc_audience="",
    )
    base.update(overrides)
    return Settings(**base)


def test_dev_open_when_nothing_configured():
    ok, reason = authorize(None, make_settings(civic_environment="dev"))
    assert ok and reason == "dev-open"


def test_prod_fails_closed_when_nothing_configured():
    ok, reason = authorize(None, make_settings(civic_environment="prod"))
    assert not ok and "not configured" in reason


def test_static_token_accepts_match_rejects_mismatch():
    s = make_settings(admin_token="s3cret")
    ok, reason = authorize("s3cret", s)
    assert ok and reason == "static-token"
    ok, reason = authorize("wrong", s)
    assert not ok and reason == "invalid admin token"
    ok, _, = authorize(None, s)
    assert not ok


def test_oidc_configured_requires_token():
    s = make_settings(oidc_issuer="https://idp.example.org")
    ok, reason = authorize(None, s)
    assert not ok and reason == "missing bearer token"


def test_static_token_takes_precedence_over_oidc_only_when_oidc_unset():
    # oidc unset, token set -> static path
    s = make_settings(admin_token="t")
    ok, reason = authorize("t", s)
    assert ok and reason == "static-token"


def test_oidc_rejects_garbage_token_without_leaking():
    # OIDC configured; a structurally invalid token must be denied, not raise.
    s = make_settings(oidc_issuer="https://idp.example.org")
    ok, reason = authorize("not.a.jwt", s)
    assert not ok and reason == "invalid token"
