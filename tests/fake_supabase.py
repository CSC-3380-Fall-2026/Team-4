"""In-memory stand-in for the Supabase client used by schedule tests."""

import re
from itertools import count
from types import SimpleNamespace
from typing import Any, Callable
from uuid import uuid4

from postgrest.exceptions import APIError

Row = dict[str, Any]
Rule = Callable[[Row], bool]


def parse_terms(text: str) -> list[tuple[str, str]]:
    """Split "a.eq.1,b.eq.2" into (column, value) pairs.

    Args:
        text: Comma separated equality terms.

    Returns:
        The (column, value) pairs.
    """
    return [
        (term.split(".eq.")[0], term.split(".eq.")[1])
        for term in text.split(",")
    ]


def parse_or(text: str) -> Rule:
    """Build a row rule from a PostgREST or_() filter string.

    Args:
        text: Either "and(...),and(...)" groups or plain equality terms.

    Returns:
        A function telling whether a row matches.
    """
    groups = re.findall(r"and\(([^)]*)\)", text)
    options = [parse_terms(group) for group in groups]
    if not options:
        options = [[term] for term in parse_terms(text)]
    return lambda row: any(
        all(str(row.get(col)) == val for col, val in option)
        for option in options
    )


class FakeDatabase:
    """Shared tables plus a small model of the row level security policies."""

    def __init__(self) -> None:
        """Create empty tables and a creation-order counter."""
        self.tables: dict[str, list[Row]] = {}
        self.clock = count(1)
        self.broken: set[str] = set()
        self.calls: list[str] = []
        self.users: dict[str, Row] = {}
        self.confirm_email: bool = False

    def rows(self, name: str) -> list[Row]:
        """Return the mutable row list of a table.

        Args:
            name: Table name.

        Returns:
            The table's rows.
        """
        return self.tables.setdefault(name, [])

    def friends(self, left: str, right: str) -> bool:
        """Tell whether two students are accepted friends.

        Args:
            left: First student id.
            right: Second student id.

        Returns:
            True for an accepted friendship in either direction.
        """
        pairs = {(left, right), (right, left)}
        return any(
            (row["requester_id"], row["addressee_id"]) in pairs
            and row["status"] == "accepted"
            for row in self.rows("friendships")
        )

    def visible(self, name: str, row: Row, uid: str) -> bool:
        """Apply the row level security policies for one student.

        Args:
            name: Table name.
            row: Row being read.
            uid: The signed-in student's id.

        Returns:
            Whether the student may see the row.
        """
        if name == "profiles":
            return row["id"] == uid
        if name == "schedules":
            return row["user_id"] == uid or self.shared(row, uid)
        if name == "forecasts":
            return row["user_id"] == uid
        if name == "friendships":
            return uid in (row["requester_id"], row["addressee_id"])
        if name == "schedule_shares":
            return uid in (row["owner_id"], row["friend_id"])
        return True

    def shared(self, row: Row, uid: str) -> bool:
        """Tell whether a schedule was shared with a student by a friend.

        Args:
            row: Schedule row.
            uid: The student's id.

        Returns:
            True when shared and the owner is an accepted friend.
        """
        given = any(
            share["schedule_id"] == row["id"] and share["friend_id"] == uid
            for share in self.rows("schedule_shares")
        )
        return given and self.friends(row["user_id"], uid)


class FakeQuery:
    """One chained table call such as table().select().eq().execute()."""

    def __init__(self, db: FakeDatabase, name: str, uid: str) -> None:
        """Start a query.

        Args:
            db: Shared fake database.
            name: Table name.
            uid: Signed-in student's id.
        """
        self.db, self.name, self.uid = db, name, uid
        self.action: str = "select"
        self.payload: Row = {}
        self.rules: list[Rule] = []
        self.sort: tuple[str, bool] | None = None
        self.key: str = "id"

    def select(self, *_args: Any) -> "FakeQuery":
        """Select rows; the column list is ignored."""
        self.action = "select"
        return self

    def insert(self, payload: Row) -> "FakeQuery":
        """Insert one row."""
        self.action, self.payload = "insert", payload
        return self

    def upsert(self, payload: Row, **kw: Any) -> "FakeQuery":
        """Insert or replace one row by id or by the on_conflict column."""
        self.action, self.payload = "upsert", payload
        self.key = kw.get("on_conflict", "id")
        return self

    def update(self, payload: Row) -> "FakeQuery":
        """Update matching rows."""
        self.action, self.payload = "update", payload
        return self

    def delete(self) -> "FakeQuery":
        """Delete matching rows."""
        self.action = "delete"
        return self

    def eq(self, column: str, value: Any) -> "FakeQuery":
        """Keep rows whose column equals a value."""
        self.rules.append(lambda row: str(row.get(column)) == str(value))
        return self

    def in_(self, column: str, values: list[Any]) -> "FakeQuery":
        """Keep rows whose column is one of the values."""
        wanted = {str(value) for value in values}
        self.rules.append(lambda row: str(row.get(column)) in wanted)
        return self

    def or_(self, text: str) -> "FakeQuery":
        """Keep rows matching a PostgREST or filter."""
        self.rules.append(parse_or(text))
        return self

    def limit(self, _size: int) -> "FakeQuery":
        """Accept and ignore a row limit."""
        return self

    def is_(self, column: str, value: str) -> "FakeQuery":
        """Keep rows whose column is null (the only use)."""
        self.rules.append(lambda row: row.get(column) is None)
        return self

    def order(self, column: str, desc: bool = False) -> "FakeQuery":
        """Sort results by a column."""
        self.sort = (column, desc)
        return self

    def matching(self) -> list[Row]:
        """Return rows the student may see that satisfy every filter."""
        return [
            row for row in self.db.rows(self.name)
            if self.db.visible(self.name, row, self.uid)
            and all(rule(row) for rule in self.rules)
        ]

    def run_select(self) -> list[Row]:
        """Return matching rows."""
        return self.matching()

    def check_unique(self, row: Row) -> None:
        """Enforce the unique index on (user_id, lower(name)) of schedules.

        Args:
            row: The row as it would be stored.

        Raises:
            APIError: With Postgres code 23505 for a second schedule name.
        """
        if self.name != "schedules":
            return
        for other in self.db.rows(self.name):
            if (
                other["id"] != row["id"]
                and other["user_id"] == row["user_id"]
                and other["name"].lower() == row["name"].lower()
            ):
                raise APIError({"code": "23505", "message": "duplicate key value"})

    def run_insert(self) -> list[Row]:
        """Store and return a new row with database defaults."""
        row = {
            "id": str(uuid4()),
            "user_id": self.uid,
            "created_at": next(self.db.clock),
            **self.payload,
        }
        self.check_unique(row)
        self.db.rows(self.name).append(row)
        return [row]

    def run_upsert(self) -> list[Row]:
        """Replace the row with the same id, or store a new one."""
        table = self.db.rows(self.name)
        wanted = self.payload.get(self.key)
        old = next(
            (r for r in table if wanted and r.get(self.key) == wanted), None
        )
        if old is None:
            return self.run_insert()
        old.update(self.payload)
        return [old]

    def run_update(self) -> list[Row]:
        """Update and return the matching rows."""
        rows = self.matching()
        for row in rows:
            self.check_unique({**row, **self.payload})
            row.update(self.payload)
        return rows

    def run_delete(self) -> list[Row]:
        """Delete and return the matching rows."""
        rows = self.matching()
        table = self.db.rows(self.name)
        table[:] = [row for row in table if row not in rows]
        return rows

    def execute(self) -> SimpleNamespace:
        """Run the query and return an object with .data."""
        if self.name in self.db.broken:
            raise RuntimeError("table unavailable")
        self.db.calls.append(self.name)
        rows = getattr(self, "run_" + self.action)()
        if self.sort:
            column, desc = self.sort
            rows = sorted(rows, key=lambda r: r[column], reverse=desc)
        return SimpleNamespace(data=[dict(row) for row in rows])


class FakeRpc:
    """One database-function call; functions bypass row level security."""

    def __init__(self, db: FakeDatabase, name: str, params: Row, uid: str) -> None:
        """Remember the call.

        Args:
            db: Shared fake database.
            name: Function name.
            params: Function arguments.
            uid: Signed-in student's id.
        """
        self.db, self.name, self.params, self.uid = db, name, params, uid

    def execute(self) -> SimpleNamespace:
        """Run the function like the SQL in database/tiger_setup.sql."""
        if self.name in self.db.broken:
            raise RuntimeError("function unavailable")
        if self.name == "profile_id_for_username":
            wanted = str(self.params.get("name", "")).lower()
            found = next(
                (
                    row["id"] for row in self.db.rows("profiles")
                    if (row.get("username") or "").lower() == wanted
                ),
                None,
            )
            return SimpleNamespace(data=found)
        if self.name == "username_taken":
            wanted = str(self.params.get("name", "")).lower()
            return SimpleNamespace(data=any(
                (row.get("username") or "").lower() == wanted
                for row in self.db.rows("profiles")
            ))
        if self.name == "friend_profiles":
            linked = {
                row["addressee_id"] if row["requester_id"] == self.uid
                else row["requester_id"]
                for row in self.db.rows("friendships")
                if self.uid in (row["requester_id"], row["addressee_id"])
            }
            return SimpleNamespace(data=[
                {"id": row["id"], "username": row.get("username")}
                for row in self.db.rows("profiles") if row["id"] in linked
            ])
        raise ValueError(f"unknown function {self.name}")


class FakeClient:
    """Fake Supabase client bound to one access token."""

    def __init__(self, db: FakeDatabase) -> None:
        """Create a client with no signed-in student.

        Args:
            db: Shared fake database.
        """
        self.db, self.uid = db, ""
        self.postgrest = SimpleNamespace(auth=self.set_token)
        self.auth = SimpleNamespace(
            get_user=self.get_user,
            sign_up=self.sign_up,
            sign_in_with_password=self.sign_in,
        )

    def set_token(self, token: str) -> None:
        """Bind the client to the student named by a token."""
        self.uid = token.removeprefix("token-")

    def get_user(self, token: str) -> SimpleNamespace:
        """Verify a token of the form token-<id>."""
        if not token.startswith("token-"):
            raise ValueError("bad token")
        uid = token.removeprefix("token-")
        return SimpleNamespace(
            user=SimpleNamespace(id=uid, email=f"{uid}@lsu.edu")
        )

    def signed_in(self, user: Row) -> SimpleNamespace:
        """Answer like Supabase Auth with the user and a session."""
        session = SimpleNamespace(
            access_token=f"token-{user['id']}", refresh_token=f"refresh-{user['id']}"
        )
        return SimpleNamespace(
            user=SimpleNamespace(
                id=user["id"], email=user["email"], user_metadata=user["meta"]
            ),
            session=session,
        )

    def sign_up(self, credentials: Row) -> SimpleNamespace:
        """Create an account and, like the original trigger, a bare profile.

        The id is the email's local part. With confirm_email set, no
        session is returned until the student signs in.
        """
        email = credentials["email"]
        user = {
            "id": email.split("@")[0],
            "email": email,
            "password": credentials["password"],
            "meta": dict(credentials.get("options", {}).get("data", {})),
        }
        self.db.users[email] = user
        self.db.rows("profiles").append({"id": user["id"], "email": email})
        answer = self.signed_in(user)
        if self.db.confirm_email:
            answer.session = None
        return answer

    def sign_in(self, credentials: Row) -> SimpleNamespace:
        """Sign in with email and password."""
        user = self.db.users.get(credentials["email"])
        if not user or user["password"] != credentials["password"]:
            from supabase_auth.errors import AuthApiError

            raise AuthApiError("Invalid login credentials", 400, "invalid_credentials")
        return self.signed_in(user)

    def table(self, name: str) -> FakeQuery:
        """Start a query on a table."""
        return FakeQuery(self.db, name, self.uid)

    def rpc(self, name: str, params: Row | None = None) -> FakeRpc:
        """Start a database-function call."""
        return FakeRpc(self.db, name, params or {}, self.uid)
