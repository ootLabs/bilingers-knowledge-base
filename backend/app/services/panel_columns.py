"""How wide the panel's text columns are, and the one way to fit a value into them.

Here rather than in `panel_auth`, which owned it first, because two services
write rows with these columns in them: the login audit (T-82) and the change
journal (T-89). While the helper lived next to one of them, the other defined
its own copy of the same numbers and sliced by hand, so widening
`panel_users.email` would have fixed one file and left the other quietly
truncating. That is the exact failure the helper exists to prevent.

No dependency either way between the two services, which is the other reason
this is its own module: `panel_auth` must not import the journal, and the
journal has no business importing the login path.
"""

from __future__ import annotations

# Each of these matches its column in `app.models.panel` and
# `app.models.audit`. Change one here and in the model together; a migration is
# what makes it true, this is what stops a writer exceeding it.
EMAIL_LIMIT = 320
IP_ADDRESS_LIMIT = 45
USER_AGENT_LIMIT = 255
DETAIL_LIMIT = 255


def truncated(value: str | None, limit: int) -> str | None:
    """Cut a value to what its column holds, for a column that allows NULL.

    Keyed by this one function so a limit only ever has to be gotten right in
    one place, not wherever a caller happens to build the row. `None` and an
    empty string both come back as `None`: a blank is not a fact worth storing
    in a column that permits nothing instead.
    """
    return value[:limit] if value else None


def required(value: str, limit: int) -> str:
    """The same cut, for a column declared NOT NULL.

    Separate from `truncated` because that one answers `None` for a blank, and
    handing a `NOT NULL` column a `None` trades a harmless empty string for an
    `IntegrityError`. In the change journal that error is swallowed by design,
    so the row would simply vanish, and a missing journal line is the one thing
    that module exists to prevent.
    """
    return value[:limit]
