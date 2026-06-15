"""KalshiClient / KalshiCredentials — RSA-PSS signing round-trip + env loading + fail-soft.

No httpx in the import path (D1/DX-01): these tests exercise signing and credential loading only,
never a network call. ``cryptography`` generates a throwaway keypair so the signature is verified
against its own public key (proves the message construction + PSS/SHA256 params are self-consistent
and match the documented Kalshi scheme).
"""

from __future__ import annotations

import base64

import pytest

from odds.kalshi_auth import (
    BASE_URL,
    PREFIX,
    KalshiAuthError,
    KalshiClient,
    KalshiCredentials,
    _normalize_pem,
)

crypto = pytest.importorskip("cryptography")  # auth needs cryptography; skip cleanly if absent


def _keypair():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    return priv, pem


def _verify(public_key, signature: bytes, message: bytes) -> None:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    public_key.verify(
        signature,
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )


def test_signed_headers_roundtrip_verifies():
    priv, pem = _keypair()
    creds = KalshiCredentials(api_key_id="kid-123", private_key_pem=pem)
    path = PREFIX + "/portfolio/balance"
    headers = creds.signed_headers("GET", path, now_ms=1_718_490_000_000)

    assert headers["KALSHI-ACCESS-KEY"] == "kid-123"
    assert headers["KALSHI-ACCESS-TIMESTAMP"] == "1718490000000"
    # The signed message is exactly timestamp + METHOD + path (no query string).
    message = (headers["KALSHI-ACCESS-TIMESTAMP"] + "GET" + path).encode("utf-8")
    sig = base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"])
    _verify(priv.public_key(), sig, message)  # raises InvalidSignature on mismatch


def test_signature_is_method_and_path_specific():
    priv, pem = _keypair()
    creds = KalshiCredentials(api_key_id="k", private_key_pem=pem)
    h = creds.signed_headers("GET", PREFIX + "/portfolio/balance", now_ms=1)
    sig = base64.b64decode(h["KALSHI-ACCESS-SIGNATURE"])
    # Verifying against a DIFFERENT path must fail (the path is part of the signed message).
    wrong = (h["KALSHI-ACCESS-TIMESTAMP"] + "GET" + PREFIX + "/portfolio/positions").encode()
    with pytest.raises(Exception):
        _verify(priv.public_key(), sig, wrong)


def test_from_env_needs_both_halves():
    _, pem = _keypair()
    assert KalshiCredentials.from_env({}) is None
    assert KalshiCredentials.from_env({"Kalshi": "kid"}) is None  # key id but no private key
    assert KalshiCredentials.from_env({"KALSHI_PRIVATE_KEY": pem}) is None  # key but no id
    creds = KalshiCredentials.from_env({"Kalshi": "kid", "KALSHI_PRIVATE_KEY": pem})
    assert creds is not None and creds.api_key_id == "kid"


def test_from_env_prefers_explicit_key_id_name():
    _, pem = _keypair()
    creds = KalshiCredentials.from_env(
        {"KALSHI_API_KEY_ID": "explicit", "Kalshi": "fallback", "KALSHI_PRIVATE_KEY": pem}
    )
    assert creds.api_key_id == "explicit"


def test_from_env_reads_pem_from_file(tmp_path):
    _, pem = _keypair()
    f = tmp_path / "kalshi.pem"
    f.write_text(pem)
    creds = KalshiCredentials.from_env({"Kalshi": "kid", "KALSHI_PRIVATE_KEY_PATH": str(f)})
    assert creds is not None
    # And it actually signs with the file-loaded key.
    h = creds.signed_headers("GET", PREFIX + "/markets", now_ms=2)
    assert h["KALSHI-ACCESS-SIGNATURE"]


def test_normalize_pem_unescapes_newlines():
    raw = "-----BEGIN PRIVATE KEY-----\\nAAAA\\n-----END PRIVATE KEY-----"
    fixed = _normalize_pem(raw)
    assert "\\n" not in fixed
    assert fixed.startswith("-----BEGIN PRIVATE KEY-----\n")
    assert fixed.endswith("-----END PRIVATE KEY-----\n")


def test_client_unauthenticated_is_fail_soft():
    client = KalshiClient(None, base_url=BASE_URL)
    assert client.authenticated is False
    # Signed reads with no creds fail soft (no network), not crash.
    assert client.get_balance() is None
    assert client.get_positions() == []


def test_client_signed_request_without_creds_raises_in_request():
    client = KalshiClient(None)
    with pytest.raises(KalshiAuthError):
        client._request("GET", PREFIX + "/portfolio/balance", signed=True)
