"""Bambu cloud account login flow.

Two-step login: request a verification code by email, then exchange the code
for an access token.
"""

import requests

BASE = "https://api.bambulab.com"


def send_verification_code(email: str) -> None:
    """Ask Bambu to email a one-time verification code to the given address.

    Raises:
        RuntimeError: If Bambu rejects the request.
    """
    r = requests.post(
        url=f"{BASE}/v1/user-service/user/sendemail/code",
        json={"email": email, "type": "codeLogin"},
    )
    if not r.ok:
        raise RuntimeError(f"sendemail/code failed: {r.status_code} {r.text}")


def login_with_code(email: str, code: str) -> dict:
    """Exchange an emailed verification code for an access token.

    Args:
        email: Bambu account email.
        code: Verification code received in email.

    Returns:
        Dict with keys accessToken, refreshToken, and expiresIn (seconds,
        typically ~7776000 which is 90 days).

    Raises:
        RuntimeError: If login fails.
    """
    r = requests.post(
        url=f"{BASE}/v1/user-service/user/login",
        json={"account": email, "code": code},
    )
    if not r.ok:
        raise RuntimeError(f"login failed: {r.status_code} {r.text}")
    return r.json()
