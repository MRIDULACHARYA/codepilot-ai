---
category: security
language: any
title: Secure coding guidelines
---
# Injection
Never build SQL with string formatting or concatenation; use parameterised queries. Never pass user input to `eval`, `exec`, `os.system`, or `subprocess(..., shell=True)`; pass argument lists with `shell=False` and validate against allow-lists. Escape output for the context it appears in (HTML, shell, SQL).

# Secrets
Never hard-code passwords, API keys or tokens. Load them from environment variables or a secret manager, and never log them. Rotate any secret that was committed.

# Deserialisation
Do not unpickle or `yaml.load` untrusted data; use JSON or `yaml.safe_load`.

# Cryptography
Use well-reviewed libraries. Prefer SHA-256 or stronger over MD5/SHA-1; use bcrypt/scrypt/argon2 for password hashing, with salts. Use the `secrets` module (not `random`) for tokens.

# Input and files
Validate and bound all external input (type, length, range). Prevent path traversal by resolving paths and checking they remain inside an allowed directory. Limit upload sizes and types.

# Least privilege
Run with minimal permissions, fail closed on errors, and keep dependencies updated.
