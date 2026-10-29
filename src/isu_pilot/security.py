"""Remove credential fields from public captures without changing timing fields."""
import re

# Handles both JSON and the escaped JSON strings in Next Flight HTML.
FIELDS=re.compile(rb'((?:access_token|refresh_token|id_token|api_key|apikey|client_secret|authorization|token)(?:\\*["\'])\s*:\s*(?:\\*["\']))([^"\'\\]+)',re.I)
BEARER=re.compile(rb'\bBearer[ \t]+[A-Za-z0-9._~+/=-]{16,}',re.I)
JWT=re.compile(rb'\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b')


def public_body(body):
    body=FIELDS.sub(lambda m:m[1]+b'[REDACTED]',body)
    body=BEARER.sub(b'Bearer [REDACTED]',body)
    return JWT.sub(b'[REDACTED]',body)
