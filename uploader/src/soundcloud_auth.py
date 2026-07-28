"""
One-time SoundCloud Authorization Code + PKCE bootstrap helper.

Usage examples:

    python src/soundcloud_auth.py authorize-url \
        --redirect-uri https://example.com/callback

    python src/soundcloud_auth.py exchange-code \
        --code YOUR_CODE \
        --code-verifier YOUR_CODE_VERIFIER \
        --redirect-uri https://example.com/callback

The script loads `config/.env` automatically, so `SOUNDCLOUD_CLIENT_ID` and
`SOUNDCLOUD_CLIENT_SECRET` can come from there.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _PROJECT_ROOT / "config" / ".env"
_AUTHORIZE_URL = "https://secure.soundcloud.com/authorize"
_TOKEN_URL = "https://secure.soundcloud.com/oauth/token"

load_dotenv(dotenv_path=_ENV_PATH)


def generate_code_verifier(length: int = 64) -> str:
    """Generate an RFC 7636-compatible PKCE code verifier."""
    if length < 43 or length > 128:
        raise ValueError("PKCE code verifier length must be between 43 and 128 characters.")

    while True:
        verifier = secrets.token_urlsafe(length)
        if 43 <= len(verifier) <= 128:
            return verifier


def generate_code_challenge(code_verifier: str) -> str:
    """Generate the S256 PKCE code challenge for a verifier."""
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def build_authorize_url(client_id: str, redirect_uri: str, code_challenge: str, state: str) -> str:
    """Build the SoundCloud authorization URL for the PKCE flow."""
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": state,
        }
    )
    return f"{_AUTHORIZE_URL}?{query}"


def exchange_code_for_tokens(
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code_verifier: str,
    code: str,
) -> dict:
    """Exchange an authorization code + PKCE verifier for SoundCloud tokens."""
    resp = requests.post(
        _TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
            "code": code,
        },
        timeout=30,
    )
    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
        detail = _response_detail(resp)
        raise RuntimeError(
            f"SoundCloud token exchange failed with HTTP {resp.status_code}: {detail}"
        ) from exc
    return resp.json()


def _response_detail(resp: requests.Response) -> str:
    try:
        payload = resp.json()
    except ValueError:
        payload = None

    if isinstance(payload, dict):
        for key in ("error_description", "error", "message"):
            value = payload.get(key)
            if value:
                return str(value)
        return str(payload)

    text = resp.text.strip()
    if text:
        return text
    return "No response body returned by SoundCloud."


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate SoundCloud PKCE values and exchange an authorization code for tokens."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    authorize = subparsers.add_parser(
        "authorize-url",
        help="Generate a PKCE verifier/challenge and print the browser authorization URL.",
    )
    authorize.add_argument(
        "--redirect-uri",
        default=os.environ.get("SOUNDCLOUD_REDIRECT_URI", "").strip(),
        help="Redirect URI registered in your SoundCloud app.",
    )
    authorize.add_argument(
        "--client-id",
        default=os.environ.get("SOUNDCLOUD_CLIENT_ID", "").strip(),
        help="SoundCloud client ID. Defaults to SOUNDCLOUD_CLIENT_ID.",
    )

    exchange = subparsers.add_parser(
        "exchange-code",
        help="Exchange the returned authorization code and verifier for tokens.",
    )
    exchange.add_argument("--code", required=True, help="Authorization code returned by SoundCloud.")
    exchange.add_argument(
        "--code-verifier",
        default=os.environ.get("SOUNDCLOUD_CODE_VERIFIER", "").strip(),
        help="Original PKCE code verifier used to build the authorize URL.",
    )
    exchange.add_argument(
        "--redirect-uri",
        default=os.environ.get("SOUNDCLOUD_REDIRECT_URI", "").strip(),
        help="Redirect URI registered in your SoundCloud app.",
    )
    exchange.add_argument(
        "--client-id",
        default=os.environ.get("SOUNDCLOUD_CLIENT_ID", "").strip(),
        help="SoundCloud client ID. Defaults to SOUNDCLOUD_CLIENT_ID.",
    )
    exchange.add_argument(
        "--client-secret",
        default=os.environ.get("SOUNDCLOUD_CLIENT_SECRET", "").strip(),
        help="SoundCloud client secret. Defaults to SOUNDCLOUD_CLIENT_SECRET.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "authorize-url":
        client_id = args.client_id or _required_env("SOUNDCLOUD_CLIENT_ID")
        redirect_uri = args.redirect_uri or _required_env("SOUNDCLOUD_REDIRECT_URI")
        code_verifier = generate_code_verifier()
        code_challenge = generate_code_challenge(code_verifier)
        state = secrets.token_urlsafe(24)
        authorize_url = build_authorize_url(client_id, redirect_uri, code_challenge, state)

        print("Open this URL in your browser:")
        print(authorize_url)
        print()
        print("Save these values before continuing:")
        print(f"SOUNDCLOUD_CODE_VERIFIER={code_verifier}")
        print(f"SOUNDCLOUD_REDIRECT_URI={redirect_uri}")
        print(f"SOUNDCLOUD_STATE={state}")
        print()
        print("After approving access, copy the `code` query parameter from the redirect URL")
        print("and run the `exchange-code` command.")
        return

    if args.command == "exchange-code":
        client_id = args.client_id or _required_env("SOUNDCLOUD_CLIENT_ID")
        client_secret = args.client_secret or _required_env("SOUNDCLOUD_CLIENT_SECRET")
        redirect_uri = args.redirect_uri or _required_env("SOUNDCLOUD_REDIRECT_URI")
        code_verifier = args.code_verifier or _required_env("SOUNDCLOUD_CODE_VERIFIER")
        try:
            payload = exchange_code_for_tokens(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                code_verifier=code_verifier,
                code=args.code,
            )
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            print(
                "Common causes: the authorization code was already used or expired, "
                "the redirect URI does not exactly match the authorize step, or the "
                "code verifier does not match the original PKCE challenge.",
                file=sys.stderr,
            )
            raise SystemExit(1)

        print("Token exchange succeeded.")
        print("Store these in config/.env:")
        print(f"SOUNDCLOUD_REFRESH_TOKEN={payload.get('refresh_token', '')}")
        print(f"SOUNDCLOUD_ACCESS_TOKEN={payload.get('access_token', '')}")
        if "expires_in" in payload:
            print(f"SOUNDCLOUD_ACCESS_TOKEN_EXPIRES_IN={payload['expires_in']}")
        return

    parser.error(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()