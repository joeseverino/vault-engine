"""Local wall-clock helpers.

Vault dates are the owner's local calendar days, so "today" is read from the
system timezone and carried as an aware datetime.
"""

from datetime import date, datetime


def local_now() -> datetime:
    return datetime.now().astimezone()


def local_today() -> date:
    return local_now().date()
