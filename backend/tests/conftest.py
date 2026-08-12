"""Injecte automatiquement le jeton superadmin dans tous les appels requests des tests."""
import requests
from dotenv import dotenv_values

_frontend_env = dotenv_values("/app/frontend/.env")
_backend_env = dotenv_values("/app/backend/.env")
_BASE = (_frontend_env.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
_token = None


def _get_token():
    global _token
    if _token is None:
        r = requests.sessions.Session().request(
            "POST", f"{_BASE}/api/auth/login",
            json={"email": _backend_env.get("ADMIN_EMAIL"),
                  "password": _backend_env.get("ADMIN_PASSWORD")},
            timeout=30)
        r.raise_for_status()
        _token = r.json()["token"]
    return _token


_orig_request = requests.sessions.Session.request


def _patched_request(self, method, url, **kwargs):
    if "/api/" in str(url) and "/api/auth/login" not in str(url):
        headers = kwargs.get("headers") or {}
        if "Authorization" not in headers:
            headers["Authorization"] = f"Bearer {_get_token()}"
        kwargs["headers"] = headers
    return _orig_request(self, method, url, **kwargs)


requests.sessions.Session.request = _patched_request
