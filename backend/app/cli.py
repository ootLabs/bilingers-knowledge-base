"""Command line entry points for operations the HTTP API deliberately lacks.

Today that is exactly one thing: creating the first administrator. The panel
has no registration form and account creation requires an administrator, so
without this there is no way to get the first one, and adding a bootstrap
endpoint would put a permanent hole in the API to solve a one-off problem.

Run it in the container:

    docker compose exec backend python -m app.cli create-admin admin@example.org

It prints a one-time setup token. No password is ever typed on a command line,
where it would land in shell history and in the process list.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable

from pydantic import TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.panel import PanelRole
from app.schemas.panel import Email
from app.services.panel_users import EmailAlreadyUsed, create_panel_user

_EMAIL_ADAPTER: TypeAdapter[str] = TypeAdapter(Email)


def _create_admin(session: Session, email: str) -> int:
    # The HTTP layer gets this for free from `PanelLoginRequest`/schemas; a CLI
    # argument has no such gate, and this is the only way the first
    # administrator ever gets created, so a typo here is otherwise permanent.
    try:
        _EMAIL_ADAPTER.validate_python(email)
    except ValidationError:
        print(f"'{email}' is not a valid email address.")
        return 1

    try:
        user, _, token = create_panel_user(session, email=email, role=PanelRole.ADMIN)
    except EmailAlreadyUsed:
        print(f"An account already exists for {email}.")
        print("Issue a password reset for it from the panel instead.")
        return 1

    print(f"Administrator account created: {user.email} (id {user.id})")
    print(f"One-time setup token: {token}")
    print("Hand it over, then have them POST it to /api/panel/password-resets/confirm.")
    return 0


def main(
    argv: list[str] | None = None,
    session_factory: Callable[[], Session] = SessionLocal,
) -> int:
    """Parse arguments and run. `session_factory` is injectable for tests."""
    parser = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    create = subcommands.add_parser("create-admin", help="create the first administrator")
    create.add_argument("email")

    arguments = parser.parse_args(argv)
    session = session_factory()
    try:
        return _create_admin(session, arguments.email)
    finally:
        session.close()


if __name__ == "__main__":  # pragma: no cover - exercised by running the module
    raise SystemExit(main())
