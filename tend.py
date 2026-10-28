"""Compatibility loader for older shortcuts; new code imports :mod:`tether`.

Keep this module while installed shortcuts may still run ``python -m tend.native``.
The implementation and package data live exclusively in the tether directory.
"""
from tether import __version__, __path__
