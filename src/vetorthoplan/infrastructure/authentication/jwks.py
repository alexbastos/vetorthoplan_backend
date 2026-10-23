from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import jwt


class JWKSUnavailableError(Exception):
    """Raised when the configured identity provider's signing keys cannot be fetched."""


class SigningKeyNotFoundError(Exception):
    """Raised when the JWKS does not contain the key identified by the token."""


class JWKSKeyProvider:
    def __init__(self, url: str, cache_seconds: int, timeout_seconds: float) -> None:
        self._url = url
        self._cache_seconds = cache_seconds
        self._timeout_seconds = timeout_seconds
        self._keys: list[dict[str, Any]] = []
        self._fetched_at = 0.0
        self._lock = asyncio.Lock()

    async def get_key(self, key_id: str) -> jwt.PyJWK:
        keys = await self._get_keys()
        matching_key = self._matching_key(keys, key_id)
        if matching_key is None:
            # A recently rotated key may not have been present in our cached JWKS.
            keys = await self._get_keys(force_refresh=True)
            matching_key = self._matching_key(keys, key_id)
        if matching_key is None:
            raise SigningKeyNotFoundError
        return jwt.PyJWK.from_dict(matching_key, algorithm="RS256")

    async def _get_keys(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        if not force_refresh and self._keys and time.monotonic() - self._fetched_at < self._cache_seconds:
            return self._keys

        async with self._lock:
            if not force_refresh and self._keys and time.monotonic() - self._fetched_at < self._cache_seconds:
                return self._keys
            try:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.get(self._url)
                    response.raise_for_status()
                    document = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise JWKSUnavailableError from exc

            keys = document.get("keys") if isinstance(document, dict) else None
            if not isinstance(keys, list) or not all(isinstance(key, dict) for key in keys):
                raise JWKSUnavailableError
            self._keys = keys
            self._fetched_at = time.monotonic()
            return self._keys

    @staticmethod
    def _matching_key(keys: list[dict[str, Any]], key_id: str) -> dict[str, Any] | None:
        for key in keys:
            if (
                key.get("kid") == key_id
                and key.get("kty") == "RSA"
                and key.get("use", "sig") == "sig"
                and key.get("alg", "RS256") == "RS256"
            ):
                return key
        return None
