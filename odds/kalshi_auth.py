"""Authenticated Kalshi client — RSA-PSS request signing (current Kalshi API-key scheme).

Kalshi's PUBLIC market data (``/markets``, ``/events``, ``/series``) is a KEYLESS read —
``odds.kalshi.KalshiWCProvider`` already fetches it with no credentials, and that is ALL the
EV monitor needs to see "current betting options". This module adds the AUTHENTICATED seam for
the two things that genuinely need the API key:

  - reading your real account **balance / positions**, so fractional-Kelly stakes size against
    your true bankroll instead of a hardcoded number (``scripts.ev_report --use-balance``);
  - (future) order placement — DELIBERATELY NOT implemented. Per docs/WORLDCUP.md §1 the monitor
    is read-only and execution is gated behind [Q-LEGAL]; this client exposes no order endpoints.

Auth scheme (Kalshi API keys, RSA — see docs/WORLDCUP.md §5 "Kalshi trading auth = RSA-PSS"):
every request carries three headers —

    KALSHI-ACCESS-KEY        the API Key ID (a UUID; the PUBLIC half of the key pair)
    KALSHI-ACCESS-TIMESTAMP  current time in MILLISECONDS since epoch, as a string
    KALSHI-ACCESS-SIGNATURE  base64( RSA-PSS-SHA256( timestamp + METHOD + path ) )

signed with your RSA PRIVATE KEY (PSS padding, MGF1-SHA256, salt length = digest length). The
message is the concatenation ``timestamp + HTTP-method + request-path`` where the path INCLUDES
the ``/trade-api/v2`` prefix and EXCLUDES the query string. The Key ID alone is NOT enough — the
private key (PEM) is required to sign, so an authenticated client needs BOTH halves.

D1/DX-01 invariant (matches odds/base.py + the providers): ``httpx`` AND ``cryptography`` are
lazy-imported INSIDE the methods that need them, NEVER at module import, so importing this module
stays cheap and dependency-free. The keyless monitor path must not pull a crypto/network import.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Production host. Kalshi consolidated its book under elections.kalshi.com; the trade API lives
# under the /trade-api/v2 prefix (the same base the keyless reader in odds/kalshi.py pages).
BASE_URL = "https://api.elections.kalshi.com"
PREFIX = "/trade-api/v2"

# Env var names recognised for the API Key ID, in priority order. ``Kalshi`` is the literal name
# the owner set in the cloud env; ``KALSHI_API_KEY_ID`` is the documented/preferred name.
_KEY_ID_VARS = ("KALSHI_API_KEY_ID", "KALSHI_ACCESS_KEY", "Kalshi", "KALSHI_API_KEY")
# Inline PEM, then path-to-PEM, in priority order.
_PEM_VARS = ("KALSHI_PRIVATE_KEY", "KALSHI_PRIVATE_KEY_PEM")
_PEM_PATH_VARS = ("KALSHI_PRIVATE_KEY_PATH", "KALSHI_PEM_PATH", "KALSHI_PRIVATE_KEY_FILE")
_PASSWORD_VARS = ("KALSHI_PRIVATE_KEY_PASSWORD", "KALSHI_PEM_PASSWORD")


class KalshiAuthError(RuntimeError):
    """Raised when an authenticated call is attempted without usable credentials."""


def _first(env: dict, names: tuple[str, ...]) -> str | None:
    for n in names:
        v = env.get(n)
        if v and str(v).strip():
            return str(v).strip()
    return None


def _normalize_pem(text: str) -> str:
    """Accept a PEM that arrived with escaped ``\\n`` (common when a key is pasted into an env var).

    If the value has no real newline but contains the literal two-character sequence backslash-n,
    convert those to real newlines so ``load_pem_private_key`` can parse it. A well-formed PEM
    (real newlines) is returned unchanged.
    """
    if "\n" not in text and "\\n" in text:
        text = text.replace("\\n", "\n")
    return text.strip() + "\n"


def _load_pem_from_env(env: dict) -> str | None:
    """Resolve the private-key PEM text from inline env, then a file path. None if absent."""
    inline = _first(env, _PEM_VARS)
    if inline:
        return _normalize_pem(inline)
    path = _first(env, _PEM_PATH_VARS)
    if path:
        try:
            return _normalize_pem(Path(path).expanduser().read_text(encoding="utf-8"))
        except OSError:
            return None
    return None


@dataclass(frozen=True)
class KalshiCredentials:
    """An API Key ID + the RSA private-key PEM that signs requests for it.

    ``password`` is the PEM passphrase (bytes) if the key is encrypted — usually ``None`` for
    Kalshi-issued keys, which are unencrypted PEM.
    """

    api_key_id: str
    private_key_pem: str
    password: bytes | None = None

    @classmethod
    def from_env(cls, env: dict | None = None) -> "KalshiCredentials | None":
        """Build from environment variables, or None if either half is missing.

        Recognises ``KALSHI_API_KEY_ID`` (and the literal ``Kalshi`` the owner set) for the Key ID,
        and ``KALSHI_PRIVATE_KEY`` (inline PEM) or ``KALSHI_PRIVATE_KEY_PATH`` (a file) for the key.
        Returns None — never raises — when credentials are absent, so the caller falls back to the
        keyless market read (fail-soft, matches the provider layer).
        """
        env = os.environ if env is None else env
        key_id = _first(env, _KEY_ID_VARS)
        pem = _load_pem_from_env(env)
        if not key_id or not pem:
            return None
        pw = _first(env, _PASSWORD_VARS)
        return cls(api_key_id=key_id, private_key_pem=pem, password=pw.encode() if pw else None)

    def signed_headers(self, method: str, path: str, *, now_ms: int | None = None) -> dict[str, str]:
        """The three Kalshi auth headers for ``METHOD path`` (path incl. /trade-api/v2, no query).

        ``cryptography`` is imported HERE (lazy, D1/DX-01). ``now_ms`` overrides the timestamp for
        deterministic testing. Signature = base64(RSA-PSS-SHA256(timestamp + METHOD + path)).
        """
        import base64
        import time

        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        key = serialization.load_pem_private_key(
            self.private_key_pem.encode("utf-8"), password=self.password
        )
        ts = str(int(time.time() * 1000) if now_ms is None else int(now_ms))
        message = (ts + method.upper() + path).encode("utf-8")
        signature = key.sign(
            message,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
        return {
            "KALSHI-ACCESS-KEY": self.api_key_id,
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode("ascii"),
        }


class KalshiClient:
    """Read-only Kalshi REST client: keyless market reads + (when keyed) signed portfolio reads.

    Construct with ``KalshiClient.from_env()`` — it picks up credentials if both the Key ID and the
    private key are present, else runs unauthenticated (``authenticated`` is False) and only the
    keyless endpoints work. Network errors fail soft to ``None``/``[]`` so the monitor never crashes
    on an outage or a blocked egress host.

    NO order-placement methods exist by design (read-only monitor; execution gated, WORLDCUP §1).
    """

    def __init__(self, credentials: KalshiCredentials | None = None, *,
                 base_url: str = BASE_URL, timeout: float = 25.0) -> None:
        self._creds = credentials
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @classmethod
    def from_env(cls, env: dict | None = None, **kwargs) -> "KalshiClient":
        return cls(KalshiCredentials.from_env(env), **kwargs)

    @property
    def authenticated(self) -> bool:
        return self._creds is not None

    def _request(self, method: str, path: str, *, params: dict | None = None,
                 signed: bool = False) -> dict:
        """One REST call. ``httpx`` lazy-imported HERE (D1/DX-01). Signs iff ``signed`` is set.

        Signing uses ``path`` ONLY (no query string), exactly as Kalshi verifies it; ``params`` go
        on the URL separately. Raises on a non-2xx or transport error (callers fail soft around it).
        """
        # Validate creds + sign BEFORE importing httpx, so a signed call with no credentials fails
        # with a clear KalshiAuthError rather than an httpx ImportError.
        headers = {"Accept": "application/json"}
        if signed:
            if self._creds is None:
                raise KalshiAuthError(
                    "authenticated call needs both KALSHI_API_KEY_ID and a private key "
                    "(KALSHI_PRIVATE_KEY / KALSHI_PRIVATE_KEY_PATH)"
                )
            headers.update(self._creds.signed_headers(method, path))

        import httpx

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.request(method, self.base_url + path, params=params, headers=headers)
            resp.raise_for_status()
            return resp.json()

    def get_balance(self) -> float | None:
        """Account balance in DOLLARS (Kalshi returns integer cents), or None on failure.

        Requires credentials. Used by ``scripts.ev_report --use-balance`` to size Kelly stakes
        against the real bankroll instead of a hardcoded ``--bankroll``.
        """
        try:
            data = self._request("GET", PREFIX + "/portfolio/balance", signed=True)
        except (KalshiAuthError, Exception):  # noqa: BLE001 — fail-soft, never crash the monitor
            return None
        cents = data.get("balance")
        try:
            return float(cents) / 100.0 if cents is not None else None
        except (TypeError, ValueError):
            return None

    def get_positions(self) -> list[dict]:
        """Open market positions (raw dicts), or [] on failure. Requires credentials."""
        try:
            data = self._request("GET", PREFIX + "/portfolio/positions", signed=True)
        except (KalshiAuthError, Exception):  # noqa: BLE001 — fail-soft
            return []
        return data.get("market_positions") or []

    def fetch_market_dicts(self, series_tickers: list[str], *, status: str = "open",
                           signed: bool | None = None) -> list[dict]:
        """Page raw market dicts across the given series (bounded), concatenated. Fail-soft to [].

        Market data is keyless, so ``signed`` defaults to False (the robust path — no clock-skew
        signature risk). Pass ``signed=True`` to authenticate the read when credentials are present.
        The returned dicts feed ``odds.kalshi.KalshiWCProvider.get_states`` unchanged.
        """
        use_signed = bool(self.authenticated) if signed is None else signed
        use_signed = use_signed and self.authenticated
        kept: list[dict] = []
        for series in series_tickers:
            cursor: str | None = None
            for _ in range(12):  # bounded paging per series
                params: dict = {"series_ticker": series, "status": status, "limit": 200}
                if cursor:
                    params["cursor"] = cursor
                try:
                    data = self._request("GET", PREFIX + "/markets", params=params, signed=use_signed)
                except Exception:  # noqa: BLE001 — per-series fail-soft
                    break
                markets = data.get("markets") or []
                kept.extend(markets)
                cursor = data.get("cursor")
                if not cursor or not markets:
                    break
        return kept
