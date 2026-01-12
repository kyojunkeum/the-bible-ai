import os
from urllib.parse import urlencode

import requests


GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_MOBILE_CLIENT_ID = os.getenv("GOOGLE_MOBILE_CLIENT_ID", "")
GOOGLE_MOBILE_CLIENT_SECRET = os.getenv("GOOGLE_MOBILE_CLIENT_SECRET", "")
GOOGLE_ALLOWED_CLIENT_IDS = os.getenv("GOOGLE_ALLOWED_CLIENT_IDS", "")
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GOOGLE_SCOPES = [
    "openid",
    "email",
    "profile",
]


def _split_env_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _allowed_google_client_ids() -> set[str]:
    ids = set(_split_env_list(GOOGLE_ALLOWED_CLIENT_IDS))
    if GOOGLE_CLIENT_ID:
        ids.add(GOOGLE_CLIENT_ID)
    if GOOGLE_MOBILE_CLIENT_ID:
        ids.add(GOOGLE_MOBILE_CLIENT_ID)
    return ids


def _client_secret_for_id(client_id: str) -> str:
    if client_id == GOOGLE_CLIENT_ID:
        return GOOGLE_CLIENT_SECRET
    if client_id == GOOGLE_MOBILE_CLIENT_ID:
        return GOOGLE_MOBILE_CLIENT_SECRET
    return ""


def resolve_google_client(requested_client_id: str | None) -> tuple[str, str]:
    if requested_client_id:
        allowed = _allowed_google_client_ids()
        if requested_client_id not in allowed:
            raise ValueError("invalid_client_id")
        return requested_client_id, _client_secret_for_id(requested_client_id)
    if GOOGLE_CLIENT_ID:
        return GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
    if GOOGLE_MOBILE_CLIENT_ID:
        return GOOGLE_MOBILE_CLIENT_ID, GOOGLE_MOBILE_CLIENT_SECRET
    raise ValueError("not_configured")


def build_google_auth_url(
    client_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str,
    code_challenge_method: str = "S256",
) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def exchange_code_for_tokens(
    code: str,
    redirect_uri: str,
    code_verifier: str,
    client_id: str,
    client_secret: str = "",
) -> dict:
    data = {
        "code": code,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
    }
    if client_secret:
        data["client_secret"] = client_secret
    res = requests.post(GOOGLE_TOKEN_URL, data=data, timeout=15)
    res.raise_for_status()
    return res.json()


def fetch_google_userinfo(access_token: str) -> dict:
    res = requests.get(
        GOOGLE_USERINFO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    res.raise_for_status()
    return res.json()
