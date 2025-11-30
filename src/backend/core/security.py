import bcrypt

def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt, ensuring it is not longer than 72 bytes.

    Args:
        password (str): The password to hash.

    Returns:
        str: The hashed password.
    """
    # Truncate the password to 72 bytes to avoid bcrypt errors
    password = password[:72]
    hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    return hashed.decode('utf-8')
