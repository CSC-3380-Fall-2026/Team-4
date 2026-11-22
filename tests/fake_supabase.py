"""In-memory stand-in for the Supabase client used by schedule tests."""

import re
from itertools import count
from types import SimpleNamespace
from typing import Any, Callable
from uuid import uuid4

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
            return row["id"] == uid or self.friends(row["id"], uid)
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

    def or_(self, text: str) -> "FakeQuery":
        """Keep rows matching a PostgREST or filter."""
        self.rules.append(parse_or(text))
        return self

    def limit(self, _size: int) -> "FakeQuery":
        """Accept and ignore a row limit."""
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

    def run_insert(self) -> list[Row]:
        """Store and return a new row with database defaults."""
        row = {
            "id": str(uuid4()),
            "user_id": self.uid,
            "created_at": next(self.db.clock),
            **self.payload,
        }
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
        self.auth = SimpleNamespace(get_user=self.get_user)

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

    def table(self, name: str) -> FakeQuery:
        """Start a query on a table."""
        return FakeQuery(self.db, name, self.uid)

    def rpc(self, name: str, params: Row | None = None) -> FakeRpc:
        """Start a database-function call."""
        return FakeRpc(self.db, name, params or {}, self.uid)
