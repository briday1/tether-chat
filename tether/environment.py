"""Branded environment configuration with legacy-name compatibility."""
import os

def get(name, default=None):
    """Prefer TETHER_* and still accept an existing TEND_* configuration."""
    if name in os.environ:
        return os.environ[name]
    legacy = "TEND_" + name[7:] if name.startswith("TETHER_") else name
    return os.environ.get(legacy, default)

def snapshot():
    """Normalize legacy settings for child services without mutating the parent."""
    values = os.environ.copy()
    for name, value in tuple(values.items()):
        if name.startswith("TEND_"):
            values.setdefault("TETHER_" + name[5:], value)
    return values
