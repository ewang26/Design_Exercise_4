import hashlib
import os
from typing import Tuple

# TODO: Hashing is somewhat slow, can we improve?
class Security:
    SALT_SIZE = 16

    @staticmethod
    def hash_password(password: str) -> Tuple[bytes, bytes]:
        """Hash a password with a random salt using SHA-256."""
        salt = os.urandom(Security.SALT_SIZE)
        hashed = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode(),
            salt,
            100000  # Number of iterations
        )
        return hashed, salt

    @staticmethod
    def verify_password(password: str, hashed: bytes, salt: bytes) -> bool:
        """Verify a password against its hash."""
        password_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode(),
            salt,
            100000
        )
        return password_hash == hashed
