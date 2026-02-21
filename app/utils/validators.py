import re

_PHONE_REGEX = re.compile(r"^\+91[6-9]\d{9}$")
_USERNAME_REGEX = re.compile(r"^[a-zA-Z0-9_]{3,20}$")


def validate_phone(phone: str) -> bool:
    """Validate Indian E.164 phone number (+91XXXXXXXXXX)."""
    return bool(_PHONE_REGEX.match(phone))


def validate_username(username: str) -> bool:
    """Validate username: 3-20 chars, alphanumeric + underscore."""
    return bool(_USERNAME_REGEX.match(username))
