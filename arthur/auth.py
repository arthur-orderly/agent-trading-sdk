"""
Arthur SDK Authentication - ED25519 signing for Orderly API.
"""

import base64
import time
from typing import Dict, Tuple

# Base58 alphabet for key decoding
BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def base58_decode(s: str) -> bytes:
    """Decode base58 string to bytes"""
    num = 0
    for char in s:
        num = num * 58 + BASE58_ALPHABET.index(char)
    
    # Convert to bytes
    result = []
    while num > 0:
        result.append(num & 0xff)
        num >>= 8
    
    # Add leading zeros
    for char in s:
        if char == "1":
            result.append(0)
        else:
            break
    
    return bytes(reversed(result))


def parse_orderly_key(key: str) -> bytes:
    """
    Parse an Orderly key in ed25519:xxx format.
    
    Args:
        key: Key in format "ed25519:base58_encoded_key"
        
    Returns:
        Raw key bytes
    """
    if key.startswith("ed25519:"):
        key = key[8:]
    return base58_decode(key)


def sign_message(secret_key: str, message: str) -> str:
    """
    Sign a message with ED25519 key.
    
    Args:
        secret_key: Orderly secret key (ed25519:xxx format)
        message: Message to sign
        
    Returns:
        Base64-encoded signature
    """
    try:
        import nacl.signing
        
        # Parse the secret key
        key_bytes = parse_orderly_key(secret_key)
        
        # Create signing key (first 32 bytes of secret key)
        signing_key = nacl.signing.SigningKey(key_bytes[:32])
        
        # Sign the message
        signed = signing_key.sign(message.encode())
        
        # Return base64-encoded signature (first 64 bytes)
        return base64.b64encode(signed.signature).decode()
        
    except ImportError:
        raise ImportError(
            "pynacl is required for signing. Install with: pip install pynacl"
        )


def generate_auth_headers(
    api_key: str,
    secret_key: str,
    account_id: str,
    method: str,
    path: str,
    body: str = "",
) -> Dict[str, str]:
    """
    Generate authenticated headers for Orderly API request.
    
    Args:
        api_key: Orderly API key
        secret_key: Orderly secret key
        account_id: Account ID
        method: HTTP method
        path: API path
        body: Request body (for POST/PUT)
        
    Returns:
        Headers dict
    """
    timestamp = int(time.time() * 1000)
    
    # Build message to sign
    message = f"{timestamp}{method.upper()}{path}{body}"
    
    # Sign message
    signature = sign_message(secret_key, message)
    
    return {
        "orderly-timestamp": str(timestamp),
        "orderly-account-id": account_id,
        "orderly-key": api_key,
        "orderly-signature": signature,
        "Content-Type": "application/json",
    }


def verify_credentials(api_key: str, secret_key: str, account_id: str) -> bool:
    """
    Verify that credentials are valid format.
    
    Args:
        api_key: Orderly API key
        secret_key: Orderly secret key
        account_id: Account ID
        
    Returns:
        True if format is valid
    """
    try:
        # Check key format
        if not api_key.startswith("ed25519:"):
            return False
        if not secret_key.startswith("ed25519:"):
            return False
        if not account_id.startswith("0x"):
            return False
        
        # Try to parse keys
        parse_orderly_key(api_key)
        parse_orderly_key(secret_key)
        
        return True
    except Exception:
        return False
