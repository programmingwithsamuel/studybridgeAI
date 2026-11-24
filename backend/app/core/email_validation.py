import re
from dataclasses import dataclass
from email.utils import parseaddr


EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$")

TYPO_DOMAINS = {
    "gmial.com": "gmail.com",
    "gmai.com": "gmail.com",
    "gmail.con": "gmail.com",
    "yahooo.com": "yahoo.com",
    "yaho.com": "yahoo.com",
    "hotnail.com": "hotmail.com",
    "outlook.con": "outlook.com",
}


@dataclass(frozen=True)
class EmailCheck:
    normalized: str
    suggestion: str | None = None
    dns_reachable: bool | None = None


def normalize_email(email: str) -> str:
    parsed = parseaddr(email.strip())[1]
    return parsed.lower()


def validate_email(email: str, allow_typo: bool = False) -> EmailCheck:
    normalized = normalize_email(email)
    if len(normalized) > 255 or not EMAIL_RE.fullmatch(normalized):
        raise ValueError("Enter a valid email address.")
    local, domain = normalized.rsplit("@", 1)
    if local.startswith(".") or local.endswith(".") or ".." in local:
        raise ValueError("Enter a valid email address.")

    suggestion = None if allow_typo else TYPO_DOMAINS.get(domain)
    if suggestion:
        suggestion = f"{local}@{suggestion}"

    return EmailCheck(normalized=normalized, suggestion=suggestion)


def validate_password(password: str) -> str:
    if len(password) < 8 or len(password) > 128:
        raise ValueError("Password must be between 8 and 128 characters.")
    if not any(char.islower() for char in password):
        raise ValueError("Password must include a lowercase letter.")
    if not any(char.isupper() for char in password):
        raise ValueError("Password must include an uppercase letter.")
    if not any(char.isdigit() for char in password):
        raise ValueError("Password must include a number.")
    if not any(not char.isalnum() for char in password):
        raise ValueError("Password must include a special character.")
    return password
