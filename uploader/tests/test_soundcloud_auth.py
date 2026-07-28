from urllib.parse import parse_qs, urlparse

import pytest
import requests

from soundcloud_auth import (
    build_authorize_url,
    exchange_code_for_tokens,
    generate_code_challenge,
    generate_code_verifier,
)


def test_generate_code_verifier_uses_valid_length():
    verifier = generate_code_verifier()

    assert 43 <= len(verifier) <= 128


def test_generate_code_verifier_rejects_invalid_length():
    with pytest.raises(ValueError, match="between 43 and 128"):
        generate_code_verifier(length=20)


def test_generate_code_challenge_matches_known_example():
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"

    challenge = generate_code_challenge(verifier)

    assert challenge == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_build_authorize_url_contains_expected_query_params():
    url = build_authorize_url(
        client_id="client123",
        redirect_uri="https://example.com/callback",
        code_challenge="challenge456",
        state="state789",
    )

    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "secure.soundcloud.com"
    assert parsed.path == "/authorize"
    assert params["client_id"] == ["client123"]
    assert params["redirect_uri"] == ["https://example.com/callback"]
    assert params["response_type"] == ["code"]
    assert params["code_challenge"] == ["challenge456"]
    assert params["code_challenge_method"] == ["S256"]
    assert params["state"] == ["state789"]


def test_exchange_code_for_tokens_surfaces_api_error_detail(mocker):
    resp = mocker.MagicMock()
    resp.status_code = 400
    resp.json.return_value = {"error": "invalid_grant"}
    resp.raise_for_status.side_effect = requests.HTTPError("400 Client Error", response=resp)
    mocker.patch("soundcloud_auth.requests.post", return_value=resp)

    with pytest.raises(RuntimeError, match="invalid_grant"):
        exchange_code_for_tokens(
            client_id="client123",
            client_secret="secret456",
            redirect_uri="https://example.com/callback",
            code_verifier="verifier789",
            code="code000",
        )