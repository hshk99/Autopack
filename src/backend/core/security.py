import bcrypt

def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt, ensuring it is not longer than 72 bytes.

    Args:
        password (str): The password to hash.

    Returns:
        str: The hashed password.
    """
    return bcrypt.hashpw(password[:72].encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
