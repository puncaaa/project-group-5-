"""
AES-256-GCM encryption and decryption.

AesGcmCipher is the single implementation used by every service.
The class is instantiated once at module level (CIPHER) and imported
as a singleton — no service needs to manage key material directly.

Wire format: Base64( nonce[16] + ciphertext[N] + tag[16] )
"""

import base64
import json
import os

from Crypto.Cipher import AES

from config.settings import CRYPTO


class AesGcmCipher:
    """
    AES-256-GCM authenticated encryption/decryption wrapper.

    All encrypt and decrypt operations use a fresh random 16-byte nonce
    per call, guaranteeing ciphertext uniqueness even for repeated values.
    The GCM authentication tag provides tamper detection.
    """

    def __init__(self, key: bytes) -> None:
        """
        Args:
            key: 32-byte AES-256 key.

        Raises:
            ValueError: If key length is not 32 bytes.
        """
        if len(key) != 32:
            raise ValueError(f"AES-256 requires a 32-byte key; got {len(key)} bytes.")
        self._key = key

    # ── Public API ─────────────────────────────────────────────────────────────

    def encrypt_int(self, value: int) -> str:
        """
        Encrypt an integer sensor reading.

        Args:
            value: Raw ADC integer value.

        Returns:
            Base64-encoded encrypted payload string.
        """
        return self._encrypt_bytes(str(value).encode("utf-8"))

    def decrypt_int(self, payload: str) -> int:
        """
        Decrypt an encrypted integer payload.

        Args:
            payload: Base64-encoded ciphertext string.

        Returns:
            Decrypted integer value.

        Raises:
            ValueError: If authentication tag verification fails (tampered data).
        """
        return int(self._decrypt_bytes(payload).decode("utf-8"))

    def encrypt_json(self, data: dict) -> str:
        """
        Serialize a dictionary to JSON and encrypt it.

        Args:
            data: Dictionary to encrypt.

        Returns:
            Base64-encoded encrypted payload string.
        """
        return self._encrypt_bytes(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def decrypt_json(self, payload: str) -> dict:
        """
        Decrypt and deserialize a JSON payload.

        Args:
            payload: Base64-encoded ciphertext string.

        Returns:
            Deserialized dictionary.

        Raises:
            ValueError: If authentication tag verification fails (tampered data).
        """
        return json.loads(self._decrypt_bytes(payload).decode("utf-8"))

    # ── Private helpers ────────────────────────────────────────────────────────

    def _encrypt_bytes(self, plaintext: bytes) -> str:
        """Encrypt raw bytes; pack nonce + ciphertext + tag into Base64."""
        nonce = os.urandom(16)
        cipher = AES.new(self._key, AES.MODE_GCM, nonce=nonce)
        ciphertext, tag = cipher.encrypt_and_digest(plaintext)
        return base64.b64encode(nonce + ciphertext + tag).decode("utf-8")

    def _decrypt_bytes(self, payload: str) -> bytes:
        """Decode Base64 payload, verify GCM tag, and return plaintext bytes."""
        raw = base64.b64decode(payload)
        nonce      = raw[:16]
        tag        = raw[-16:]
        ciphertext = raw[16:-16]
        cipher = AES.new(self._key, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag)

    def __repr__(self) -> str:
        return f"AesGcmCipher(key_length={len(self._key) * 8}-bit)"


# ── Module-level singleton ─────────────────────────────────────────────────────
# Import this; do not instantiate AesGcmCipher directly in services.

CIPHER = AesGcmCipher(CRYPTO.aes_key)
