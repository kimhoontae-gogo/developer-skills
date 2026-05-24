#!/usr/bin/env python3
"""SQLite-backed storage and export helpers for the plan skill."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

SCHEMA_VERSION = 1

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    schema_version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK (status IN ('active', 'archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT NULL
);

CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    title TEXT NOT NULL,
    goal TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('not_started', 'in_progress', 'completed', 'archived')),
    summary TEXT NOT NULL DEFAULT '',
    current_phase_id INTEGER NULL REFERENCES phases(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT NULL
);

CREATE TABLE IF NOT EXISTS phases (
    id INTEGER PRIMARY KEY,
    plan_id INTEGER NOT NULL REFERENCES plans(id) ON DELETE RESTRICT,
    position INTEGER NOT NULL,
    title TEXT NOT NULL,
    detail TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('todo', 'in_progress', 'done')),
    started_at TEXT NULL,
    completed_at TEXT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT NULL,
    UNIQUE (plan_id, position)
);

CREATE TABLE IF NOT EXISTS plan_events (
    id INTEGER PRIMARY KEY,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('project', 'plan', 'phase')),
    entity_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_projects_name ON projects(name);
CREATE INDEX IF NOT EXISTS idx_plans_project_status ON plans(project_id, status);
CREATE INDEX IF NOT EXISTS idx_plans_project_updated_at ON plans(project_id, updated_at);
CREATE INDEX IF NOT EXISTS idx_phases_plan_position ON phases(plan_id, position);
CREATE INDEX IF NOT EXISTS idx_phases_plan_status ON phases(plan_id, status);
CREATE INDEX IF NOT EXISTS idx_plan_events_entity ON plan_events(entity_type, entity_id, created_at);
"""


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


@dataclass(frozen=True)
class PlanDetail:
    project: dict[str, Any]
    plan: dict[str, Any]
    phases: list[dict[str, Any]]


class PlanStore:
    def __init__(self, db_path: str | os.PathLike[str]):
        self.db_path = Path(db_path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def ensure_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA_SQL)
            row = conn.execute("SELECT schema_version FROM schema_meta WHERE id = 1").fetchone()
            now = utc_now()
            if row is None:
                conn.execute(
                    "INSERT INTO schema_meta (id, schema_version, created_at, updated_at) VALUES (1, ?, ?, ?)",
                    (SCHEMA_VERSION, now, now),
                )
            elif int(row["schema_version"]) != SCHEMA_VERSION:
                conn.execute(
                    "UPDATE schema_meta SET schema_version = ?, updated_at = ? WHERE id = 1",
                    (SCHEMA_VERSION, now),
                )

    def _event(self, conn: sqlite3.Connection, entity_type: str, entity_id: int, event_type: str, payload: dict[str, Any]) -> None:
        conn.execute(
            """
            INSERT INTO plan_events (entity_type, entity_id, event_type, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (entity_type, entity_id, event_type, json.dumps(payload, ensure_ascii=True, sort_keys=True), utc_now()),
        )

    def _get_project(self, conn: sqlite3.Connection, *, project_id: int | None = None, name: str | None = None) -> dict[str, Any]:
        if project_id is not None:
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        elif name is not None:
            row = conn.execute("SELECT * FROM projects WHERE name = ?", (name,)).fetchone()
        else:
            raise ValueError("project_id or name is required")
        project = row_to_dict(row)
        if project is None:
            raise ValueError("project not found")
        return project

    def _get_plan(self, conn: sqlite3.Connection, plan_id: int) -> dict[str, Any]:
        row = conn.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
        plan = row_to_dict(row)
        if plan is None:
            raise ValueError("plan not found")
        return plan

    def _get_phase(self, conn: sqlite3.Connection, phase_id: int) -> dict[str, Any]:
        row = conn.execute("SELECT * FROM phases WHERE id = ?", (phase_id,)).fetchone()
        phase = row_to_dict(row)
        if phase is None:
            raise ValueError("phase not found")
        return phase

    def _plan_phases(self, conn: sqlite3.Connection, plan_id: int, *, include_archived: bool = False) -> list[dict[str, Any]]:
        query = "SELECT * FROM phases WHERE plan_id = ?"
        params: list[Any] = [plan_id]
        if not include_archived:
            query += " AND archived_at IS NULL"
        query += " ORDER BY position ASC, id ASC"
        return [dict(row) for row in conn.execute(query, params).fetchall()]

    def _resequence(self, conn: sqlite3.Connection, plan_id: int) -> None:
        phases = self._plan_phases(conn, plan_id, include_archived=False)
        for index, phase in enumerate(phases, start=1):
            if phase["position"] != index:
                conn.execute("UPDATE phases SET position = ?, updated_at = ? WHERE id = ?", (index, utc_now(), phase["id"]))

    def _rewrite_order(self, conn: sqlite3.Connection, plan_id: int, ordered_phase_ids: Sequence[int]) -> None:
        now = utc_now()
        conn.execute(
            "UPDATE phases SET position = position + 1000000, updated_at = ? WHERE plan_id = ? AND archived_at IS NULL",
            (now, plan_id),
        )
        for index, phase_id in enumerate(ordered_phase_ids, start=1):
            conn.execute("UPDATE phases SET position = ?, updated_at = ? WHERE id = ?", (index, utc_now(), phase_id))

    def _active_phase_statuses(self, phases: Sequence[dict[str, Any]]) -> list[str]:
        return [phase["status"] for phase in phases if phase["archived_at"] is None]

    def _plan_summary(self, phases: Sequence[dict[str, Any]]) -> str:
        active = [phase for phase in phases if phase["archived_at"] is None]
        counts = {"todo": 0, "in_progress": 0, "done": 0}
        for phase in active:
            counts[phase["status"]] += 1
        return f"{counts['done']} done, {counts['in_progress']} in progress, {counts['todo']} todo"

    def recompute_plan(self, conn: sqlite3.Connection, plan_id: int) -> None:
        plan = self._get_plan(conn, plan_id)
        phases = self._plan_phases(conn, plan_id, include_archived=False)
        active_statuses = self._active_phase_statuses(phases)
        if active_statuses.count("in_progress") > 1:
            raise ValueError("at most one phase may be in_progress")

        current_phase_id = next((phase["id"] for phase in phases if phase["status"] == "in_progress"), None)
        if plan["archived_at"] is not None:
            plan_status = "archived"
        elif not phases:
            plan_status = "not_started"
        elif all(status == "done" for status in active_statuses):
            plan_status = "completed"
        elif any(status in {"done", "in_progress"} for status in active_statuses):
            plan_status = "in_progress"
        else:
            plan_status = "not_started"

        conn.execute(
            """
            UPDATE plans
            SET status = ?, summary = ?, current_phase_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (plan_status, self._plan_summary(phases), current_phase_id, utc_now(), plan_id),
        )

    def create_project(self, name: str, description: str = "") -> dict[str, Any]:
        with self.connect() as conn:
            now = utc_now()
            cursor = conn.execute(
                """
                INSERT INTO projects (name, description, status, created_at, updated_at)
                VALUES (?, ?, 'active', ?, ?)
                """,
                (name, description, now, now),
            )
            project = self._get_project(conn, project_id=cursor.lastrowid)
            self._event(conn, "project", project["id"], "create", {"name": name})
            return project

    def update_project(
        self,
        project_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        with self.connect() as conn:
            project = self._get_project(conn, project_id=project_id)
            updates: list[str] = []
            params: list[Any] = []
            if name is not None:
                updates.append("name = ?")
                params.append(name)
            if description is not None:
                updates.append("description = ?")
                params.append(description)
            if status is not None:
                if status not in {"active", "archived"}:
                    raise ValueError("invalid project status")
                updates.append("status = ?")
                params.append(status)
                if status == "archived":
                    updates.append("archived_at = ?")
                    params.append(utc_now())
                else:
                    updates.append("archived_at = NULL")
            if not updates:
                return project
            updates.append("updated_at = ?")
            params.append(utc_now())
            params.append(project_id)
            conn.execute(f"UPDATE projects SET {', '.join(updates)} WHERE id = ?", params)
            updated = self._get_project(conn, project_id=project_id)
            self._event(conn, "project", project_id, "update", {k: v for k, v in {"name": name, "description": description, "status": status}.items() if v is not None})
            return updated

    def list_projects(self, *, include_archived: bool = False) -> list[dict[str, Any]]:
        with self.connect() as conn:
            query = "SELECT * FROM projects"
            if not include_archived:
                query += " WHERE archived_at IS NULL"
            query += " ORDER BY id ASC"
            return [dict(row) for row in conn.execute(query).fetchall()]

    def show_project(self, project_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            return self._get_project(conn, project_id=project_id)

    def show_project_detail(self, project_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            project = self._get_project(conn, project_id=project_id)
            plans = [dict(row) for row in conn.execute(
                "SELECT * FROM plans WHERE project_id = ? ORDER BY updated_at DESC, id DESC",
                (project_id,),
            ).fetchall()]
            return {"project": project, "plans": plans}

    def create_plan(
        self,
        project_id: int,
        title: str,
        goal: str,
        phases: Iterable[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        with self.connect() as conn:
            self._get_project(conn, project_id=project_id)
            now = utc_now()
            cursor = conn.execute(
                """
                INSERT INTO plans (project_id, title, goal, status, summary, created_at, updated_at)
                VALUES (?, ?, ?, 'not_started', '', ?, ?)
                """,
                (project_id, title, goal, now, now),
            )
            plan_id = cursor.lastrowid
            if phases:
                for position, phase in enumerate(phases, start=1):
                    conn.execute(
                        """
                        INSERT INTO phases (plan_id, position, title, detail, status, created_at, updated_at)
                        VALUES (?, ?, ?, ?, 'todo', ?, ?)
                        """,
                        (plan_id, position, phase["title"], phase["detail"], now, now),
                    )
            self.recompute_plan(conn, plan_id)
            plan = self._get_plan(conn, plan_id)
            self._event(conn, "plan", plan_id, "create", {"project_id": project_id, "title": title, "goal": goal})
            return plan

    def update_plan(
        self,
        plan_id: int,
        *,
        title: str | None = None,
        goal: str | None = None,
    ) -> dict[str, Any]:
        with self.connect() as conn:
            plan = self._get_plan(conn, plan_id)
            updates: list[str] = []
            params: list[Any] = []
            if title is not None:
                updates.append("title = ?")
                params.append(title)
            if goal is not None:
                updates.append("goal = ?")
                params.append(goal)
            if not updates:
                return plan
            updates.append("updated_at = ?")
            params.append(utc_now())
            params.append(plan_id)
            conn.execute(f"UPDATE plans SET {', '.join(updates)} WHERE id = ?", params)
            updated = self._get_plan(conn, plan_id)
            self._event(conn, "plan", plan_id, "update", {k: v for k, v in {"title": title, "goal": goal}.items() if v is not None})
            return updated

    def archive_plan(self, plan_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            self._get_plan(conn, plan_id)
            now = utc_now()
            conn.execute(
                "UPDATE plans SET status = 'archived', archived_at = ?, updated_at = ? WHERE id = ?",
                (now, now, plan_id),
            )
            self._event(conn, "plan", plan_id, "archive", {})
            return self._get_plan(conn, plan_id)

    def list_active_plans(self, *, project_id: int | None = None) -> list[dict[str, Any]]:
        with self.connect() as conn:
            query = "SELECT * FROM plans WHERE archived_at IS NULL"
            params: list[Any] = []
            if project_id is not None:
                query += " AND project_id = ?"
                params.append(project_id)
            query += " ORDER BY updated_at DESC, id DESC"
            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def show_plan_detail(self, plan_id: int) -> PlanDetail:
        with self.connect() as conn:
            plan = self._get_plan(conn, plan_id)
            project = self._get_project(conn, project_id=plan["project_id"])
            phases = self._plan_phases(conn, plan_id, include_archived=False)
            return PlanDetail(project=project, plan=plan, phases=phases)

    def show_phase(self, phase_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            phase = self._get_phase(conn, phase_id)
            plan = self._get_plan(conn, phase["plan_id"])
            project = self._get_project(conn, project_id=plan["project_id"])
            return {"project": project, "plan": plan, "phase": phase}

    def _insert_phase_record(
        self,
        conn: sqlite3.Connection,
        *,
        plan_id: int,
        position: int,
        title: str,
        detail: str,
    ) -> dict[str, Any]:
        now = utc_now()
        cursor = conn.execute(
            """
            INSERT INTO phases (plan_id, position, title, detail, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'todo', ?, ?)
            """,
            (plan_id, position, title, detail, now, now),
        )
        phase = self._get_phase(conn, cursor.lastrowid)
        self._event(conn, "phase", phase["id"], "create", {"plan_id": plan_id, "position": position, "title": title})
        return phase

    def add_phase(self, plan_id: int, title: str, detail: str) -> dict[str, Any]:
        with self.connect() as conn:
            plan = self._get_plan(conn, plan_id)
            if plan["archived_at"] is not None:
                raise ValueError("cannot modify an archived plan")
            phases = self._plan_phases(conn, plan_id, include_archived=False)
            phase = self._insert_phase_record(conn, plan_id=plan_id, position=10**9, title=title, detail=detail)
            ordered_ids = [item["id"] for item in phases] + [phase["id"]]
            self._rewrite_order(conn, plan_id, ordered_ids)
            self.recompute_plan(conn, plan_id)
            return self._get_phase(conn, phase["id"])

    def insert_phase(
        self,
        plan_id: int,
        title: str,
        detail: str,
        *,
        before_phase_id: int | None = None,
        after_phase_id: int | None = None,
    ) -> dict[str, Any]:
        if (before_phase_id is None) == (after_phase_id is None):
            raise ValueError("specify exactly one of before_phase_id or after_phase_id")
        with self.connect() as conn:
            plan = self._get_plan(conn, plan_id)
            if plan["archived_at"] is not None:
                raise ValueError("cannot modify an archived plan")

            target_id = before_phase_id if before_phase_id is not None else after_phase_id
            target = self._get_phase(conn, target_id)
            if target["plan_id"] != plan_id:
                raise ValueError("target phase must belong to the same plan")
            if target["status"] != "todo":
                raise ValueError("phases may only be inserted relative to todo phases")
            phase = self._insert_phase_record(conn, plan_id=plan_id, position=10**9, title=title, detail=detail)
            phases = self._plan_phases(conn, plan_id, include_archived=False)
            ordered_ids = [item["id"] for item in phases if item["id"] != phase["id"]]
            target_index = ordered_ids.index(target_id)
            insert_index = target_index if before_phase_id is not None else target_index + 1
            ordered_ids.insert(insert_index, phase["id"])
            self._rewrite_order(conn, plan_id, ordered_ids)
            self.recompute_plan(conn, plan_id)
            return self._get_phase(conn, phase["id"])

    def move_phase(
        self,
        phase_id: int,
        *,
        before_phase_id: int | None = None,
        after_phase_id: int | None = None,
    ) -> list[dict[str, Any]]:
        if (before_phase_id is None) == (after_phase_id is None):
            raise ValueError("specify exactly one of before_phase_id or after_phase_id")
        with self.connect() as conn:
            phase = self._get_phase(conn, phase_id)
            if phase["archived_at"] is not None:
                raise ValueError("cannot move an archived phase")
            if phase["status"] != "todo":
                raise ValueError("only todo phases may be moved")

            plan_id = phase["plan_id"]
            phases = self._plan_phases(conn, plan_id, include_archived=False)
            source = next((item for item in phases if item["id"] == phase_id), None)
            if source is None:
                raise ValueError("source phase not found")

            target_id = before_phase_id if before_phase_id is not None else after_phase_id
            target = next((item for item in phases if item["id"] == target_id), None)
            if target is None:
                raise ValueError("target phase not found")
            if target["id"] == phase_id:
                raise ValueError("cannot move a phase relative to itself")
            if target["plan_id"] != plan_id:
                raise ValueError("target phase must belong to the same plan")
            if target["status"] != "todo":
                raise ValueError("phases may only be moved relative to todo phases")

            todo_ids = [item["id"] for item in phases if item["status"] == "todo" and item["id"] != phase_id]
            target_index = todo_ids.index(target_id)
            insert_index = target_index if before_phase_id is not None else target_index + 1
            todo_ids.insert(insert_index, phase_id)
            locked_ids = [item["id"] for item in phases if item["status"] != "todo"]
            self._rewrite_order(conn, plan_id, locked_ids + todo_ids)
            self.recompute_plan(conn, plan_id)
            return self._plan_phases(conn, plan_id, include_archived=False)

    def update_phase(
        self,
        phase_id: int,
        *,
        title: str | None = None,
        detail: str | None = None,
    ) -> dict[str, Any]:
        with self.connect() as conn:
            phase = self._get_phase(conn, phase_id)
            if phase["archived_at"] is not None:
                raise ValueError("cannot modify an archived phase")
            updates: list[str] = []
            params: list[Any] = []
            if title is not None:
                updates.append("title = ?")
                params.append(title)
            if detail is not None:
                updates.append("detail = ?")
                params.append(detail)
            if not updates:
                return phase
            updates.append("updated_at = ?")
            params.append(utc_now())
            params.append(phase_id)
            conn.execute(f"UPDATE phases SET {', '.join(updates)} WHERE id = ?", params)
            updated = self._get_phase(conn, phase_id)
            self._event(conn, "phase", phase_id, "update", {k: v for k, v in {"title": title, "detail": detail}.items() if v is not None})
            return updated

    def start_phase(self, phase_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            phase = self._get_phase(conn, phase_id)
            if phase["archived_at"] is not None:
                raise ValueError("cannot start an archived phase")
            if phase["status"] != "todo":
                raise ValueError("only todo phases may be started")
            plan_id = phase["plan_id"]
            phases = self._plan_phases(conn, plan_id, include_archived=False)
            if any(item["status"] == "in_progress" for item in phases):
                raise ValueError("a plan may have only one in_progress phase")
            first_todo = next((item for item in phases if item["status"] == "todo"), None)
            if first_todo is None or first_todo["id"] != phase_id:
                raise ValueError("only the first todo phase may be started")
            now = utc_now()
            conn.execute(
                "UPDATE phases SET status = 'in_progress', started_at = COALESCE(started_at, ?), updated_at = ? WHERE id = ?",
                (now, now, phase_id),
            )
            self._event(conn, "phase", phase_id, "start", {})
            self.recompute_plan(conn, plan_id)
            return self._get_phase(conn, phase_id)

    def complete_phase(self, phase_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            phase = self._get_phase(conn, phase_id)
            if phase["archived_at"] is not None:
                raise ValueError("cannot complete an archived phase")
            if phase["status"] != "in_progress":
                raise ValueError("only in_progress phases may be completed")
            now = utc_now()
            conn.execute(
                "UPDATE phases SET status = 'done', completed_at = COALESCE(completed_at, ?), updated_at = ? WHERE id = ?",
                (now, now, phase_id),
            )
            self._event(conn, "phase", phase_id, "complete", {})
            self.recompute_plan(conn, phase["plan_id"])
            return self._get_phase(conn, phase_id)

    def archive_phase(self, phase_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            phase = self._get_phase(conn, phase_id)
            now = utc_now()
            conn.execute(
                "UPDATE phases SET archived_at = ?, updated_at = ? WHERE id = ?",
                (now, now, phase_id),
            )
            self._event(conn, "phase", phase_id, "archive", {})
            remaining_ids = [item["id"] for item in self._plan_phases(conn, phase["plan_id"], include_archived=False) if item["id"] != phase_id]
            self._rewrite_order(conn, phase["plan_id"], remaining_ids)
            self.recompute_plan(conn, phase["plan_id"])
            return self._get_phase(conn, phase_id)

    def export_plan_markdown(self, plan_id: int) -> str:
        detail = self.show_plan_detail(plan_id)
        plan = detail.plan
        phases = detail.phases
        lines = [
            f"# {plan['title']}",
            "",
            "## Goal",
            plan["goal"],
            "",
            "## Status",
            f"- Plan: {plan['status']}",
            f"- Current Phase: {next((phase['title'] for phase in phases if phase['id'] == plan['current_phase_id']), 'None')}",
        ]
        for index, phase in enumerate(phases, start=1):
            lines.append(f"- Phase {index}: {phase['status']}")
        lines.extend(["", "## Phases"])
        for index, phase in enumerate(phases, start=1):
            lines.extend(
                [
                    f"### Phase {index}. {phase['title']}",
                    phase["detail"],
                    "",
                ]
            )
        if lines and lines[-1] == "":
            lines.pop()
        return "\n".join(lines)


def resolve_db_path(value: str | None) -> Path:
    if value:
        return Path(value)
    env = os.environ.get("PLAN_DB_PATH")
    if env:
        return Path(env)
    return Path.cwd() / "plan.sqlite3"


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))


def _print_plan_detail(detail: PlanDetail) -> None:
    project = detail.project
    plan = detail.plan
    phases = detail.phases
    current_phase = next((phase for phase in phases if phase["id"] == plan["current_phase_id"]), None)
    print(f"Project: {project['name']} (#{project['id']})")
    print(f"Plan: {plan['title']} (#{plan['id']})")
    print(f"Goal: {plan['goal']}")
    print(f"Status: {plan['status']}")
    print(f"Current phase: {current_phase['title']} (#{current_phase['id']})" if current_phase else "Current phase: None")
    print(f"Summary: {plan['summary']}")
    print("Phases:")
    for phase in phases:
        marker = "*" if phase["id"] == plan["current_phase_id"] else "-"
        print(f"  {marker} [{phase['position']}] {phase['title']} #{phase['id']} :: {phase['status']}")
        detail_text = phase["detail"].replace("\n", "\n    ")
        print(f"    {detail_text}")


def _print_phase_detail(payload: dict[str, Any]) -> None:
    project = payload["project"]
    plan = payload["plan"]
    phase = payload["phase"]
    print(f"Project: {project['name']} (#{project['id']})")
    print(f"Plan: {plan['title']} (#{plan['id']})")
    print(f"Phase: {phase['title']} (#{phase['id']})")
    print(f"Position: {phase['position']}")
    print(f"Status: {phase['status']}")
    print(f"Detail: {phase['detail']}")
    print(f"Started at: {phase['started_at'] or 'None'}")
    print(f"Completed at: {phase['completed_at'] or 'None'}")
    print(f"Archived at: {phase['archived_at'] or 'None'}")


def _print_project_detail(payload: dict[str, Any]) -> None:
    project = payload["project"]
    plans = payload["plans"]
    active_plans = [plan for plan in plans if plan["archived_at"] is None]
    archived_plans = [plan for plan in plans if plan["archived_at"] is not None]
    print(f"Project: {project['name']} (#{project['id']})")
    print(f"Description: {project['description']}")
    print(f"Status: {project['status']}")
    print(f"Archived at: {project['archived_at'] or 'None'}")
    print(f"Plans: {len(plans)} total, {len(active_plans)} active, {len(archived_plans)} archived")
    if plans:
        print("Plan list:")
        for plan in plans:
            label = "archived" if plan["archived_at"] else plan["status"]
            print(f"  - {plan['title']} #{plan['id']} :: {label}")


def _parse_json_object(value: str) -> dict[str, Any]:
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("expected a JSON object")
    return payload


def _phase_payloads(values: Iterable[str] | None) -> list[dict[str, str]]:
    if not values:
        return []
    payloads: list[dict[str, str]] = []
    for raw in values:
        payload = _parse_json_object(raw)
        title = payload.get("title")
        detail = payload.get("detail")
        if not isinstance(title, str) or not isinstance(detail, str):
            raise ValueError('phase JSON must include string fields "title" and "detail"')
        payloads.append({"title": title, "detail": detail})
    return payloads


def _optional_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    lowered = value.lower()
    if lowered in {"1", "true", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError("expected a boolean value")


def _parse_patch(value: str | None) -> dict[str, Any]:
    if value is None:
        return {}
    payload = _parse_json_object(value)
    return payload


def _patch_str(payload: dict[str, Any], key: str) -> str | None:
    if key not in payload:
        return None
    value = payload[key]
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f'patch field "{key}" must be a string')
    return value


def cmd_init_db(args: argparse.Namespace) -> None:
    store = PlanStore(resolve_db_path(args.db))
    store.ensure_schema()
    print(str(store.db_path))


def cmd_create_project(args: argparse.Namespace) -> None:
    store = PlanStore(resolve_db_path(args.db))
    _print_json(store.create_project(args.name, args.description or ""))


def cmd_update_project(args: argparse.Namespace) -> None:
    store = PlanStore(resolve_db_path(args.db))
    status = None if args.status is None else args.status
    _print_json(
        store.update_project(
            args.project_id,
            name=args.name,
            description=args.description,
            status=status,
        )
    )


def cmd_list_projects(args: argparse.Namespace) -> None:
    store = PlanStore(resolve_db_path(args.db))
    _print_json(store.list_projects(include_archived=args.include_archived))


def cmd_show_project(args: argparse.Namespace) -> None:
    store = PlanStore(resolve_db_path(args.db))
    with store.connect() as conn:
        if args.project_id is not None:
            project = store._get_project(conn, project_id=args.project_id)
        else:
            project = store._get_project(conn, name=args.name)
    if args.json:
        _print_json(store.show_project_detail(project["id"]))
    else:
        _print_project_detail(store.show_project_detail(project["id"]))


def cmd_list_active_plans(args: argparse.Namespace) -> None:
    store = PlanStore(resolve_db_path(args.db))
    _print_json(store.list_active_plans(project_id=args.project_id))


def cmd_create_plan(args: argparse.Namespace) -> None:
    store = PlanStore(resolve_db_path(args.db))
    phases = _phase_payloads(args.phase)
    _print_json(store.create_plan(args.project_id, args.title, args.goal, phases=phases or None))


def cmd_update_plan(args: argparse.Namespace) -> None:
    store = PlanStore(resolve_db_path(args.db))
    patch = _parse_patch(args.patch)
    title = args.title if args.title is not None else _patch_str(patch, "title")
    goal = args.goal if args.goal is not None else _patch_str(patch, "goal")
    _print_json(store.update_plan(args.plan_id, title=title, goal=goal))


def cmd_archive_plan(args: argparse.Namespace) -> None:
    store = PlanStore(resolve_db_path(args.db))
    _print_json(store.archive_plan(args.plan_id))


def cmd_show_plan(args: argparse.Namespace) -> None:
    store = PlanStore(resolve_db_path(args.db))
    detail = store.show_plan_detail(args.plan_id)
    if args.json:
        _print_json({"project": detail.project, "plan": detail.plan, "phases": detail.phases})
    else:
        _print_plan_detail(detail)


def cmd_show_phase(args: argparse.Namespace) -> None:
    store = PlanStore(resolve_db_path(args.db))
    payload = store.show_phase(args.phase_id)
    if args.json:
        _print_json(payload)
    else:
        _print_phase_detail(payload)


def cmd_add_phase(args: argparse.Namespace) -> None:
    store = PlanStore(resolve_db_path(args.db))
    _print_json(store.add_phase(args.plan_id, args.title, args.detail))


def cmd_insert_phase(args: argparse.Namespace) -> None:
    store = PlanStore(resolve_db_path(args.db))
    before_phase_id = args.before_phase_id
    after_phase_id = args.after_phase_id
    _print_json(
        store.insert_phase(
            args.plan_id,
            args.title,
            args.detail,
            before_phase_id=before_phase_id,
            after_phase_id=after_phase_id,
        )
    )


def cmd_move_phase(args: argparse.Namespace) -> None:
    store = PlanStore(resolve_db_path(args.db))
    _print_json(
        store.move_phase(
            args.phase_id,
            before_phase_id=args.before_phase_id,
            after_phase_id=args.after_phase_id,
        )
    )


def cmd_update_phase(args: argparse.Namespace) -> None:
    store = PlanStore(resolve_db_path(args.db))
    patch = _parse_patch(args.patch)
    title = args.title if args.title is not None else _patch_str(patch, "title")
    detail = args.detail if args.detail is not None else _patch_str(patch, "detail")
    _print_json(store.update_phase(args.phase_id, title=title, detail=detail))


def cmd_start_phase(args: argparse.Namespace) -> None:
    store = PlanStore(resolve_db_path(args.db))
    _print_json(store.start_phase(args.phase_id))


def cmd_complete_phase(args: argparse.Namespace) -> None:
    store = PlanStore(resolve_db_path(args.db))
    _print_json(store.complete_phase(args.phase_id))


def cmd_archive_phase(args: argparse.Namespace) -> None:
    store = PlanStore(resolve_db_path(args.db))
    _print_json(store.archive_phase(args.phase_id))


def cmd_export_markdown(args: argparse.Namespace) -> None:
    store = PlanStore(resolve_db_path(args.db))
    print(store.export_plan_markdown(args.plan_id))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SQLite store utilities for the plan skill")
    parser.add_argument("--db", help="SQLite database path")
    sub = parser.add_subparsers(dest="command", required=True)

    init_db = sub.add_parser("init-db", help="create or migrate the database schema")
    init_db.set_defaults(func=cmd_init_db)

    create_project = sub.add_parser("create-project", help="create a project")
    create_project.add_argument("--name", required=True)
    create_project.add_argument("--description")
    create_project.set_defaults(func=cmd_create_project)

    update_project = sub.add_parser("update-project", help="update a project")
    update_project.add_argument("--project-id", type=int, required=True)
    update_project.add_argument("--name")
    update_project.add_argument("--description")
    update_project.add_argument("--status", choices=["active", "archived"])
    update_project.set_defaults(func=cmd_update_project)

    list_projects = sub.add_parser("list-projects", help="list projects")
    list_projects.add_argument("--include-archived", action="store_true")
    list_projects.set_defaults(func=cmd_list_projects)

    show_project = sub.add_parser("show-project", help="show a project")
    show_project.add_argument("--project-id", type=int)
    show_project.add_argument("--name")
    show_project.add_argument("--json", action="store_true", help="output JSON instead of human-readable text")
    show_project.set_defaults(func=cmd_show_project)

    create_plan = sub.add_parser("create-plan", help="create a plan")
    create_plan.add_argument("--project-id", type=int, required=True)
    create_plan.add_argument("--title", required=True)
    create_plan.add_argument("--goal", required=True)
    create_plan.add_argument(
        "--phase",
        action="append",
        help='phase JSON object, e.g. \'{"title":"Design","detail":"..."}\'',
    )
    create_plan.set_defaults(func=cmd_create_plan)

    update_plan = sub.add_parser("update-plan", help="update a plan")
    update_plan.add_argument("--plan-id", type=int, required=True)
    update_plan.add_argument("--title")
    update_plan.add_argument("--goal")
    update_plan.add_argument("--patch", help='JSON object, e.g. \'{"title":"New title","goal":"New goal"}\'')
    update_plan.set_defaults(func=cmd_update_plan)

    archive_plan = sub.add_parser("archive-plan", help="archive a plan")
    archive_plan.add_argument("--plan-id", type=int, required=True)
    archive_plan.set_defaults(func=cmd_archive_plan)

    list_plans = sub.add_parser("list-active-plans", help="list active plans")
    list_plans.add_argument("--project-id", type=int)
    list_plans.set_defaults(func=cmd_list_active_plans)

    show_plan = sub.add_parser("show-plan", help="show a plan detail view")
    show_plan.add_argument("--plan-id", type=int, required=True)
    show_plan.add_argument("--json", action="store_true", help="output JSON instead of human-readable text")
    show_plan.set_defaults(func=cmd_show_plan)

    show_phase = sub.add_parser("show-phase", help="show a phase detail view")
    show_phase.add_argument("--phase-id", type=int, required=True)
    show_phase.add_argument("--json", action="store_true", help="output JSON instead of human-readable text")
    show_phase.set_defaults(func=cmd_show_phase)

    add_phase = sub.add_parser("add-phase", help="append a todo phase to a plan")
    add_phase.add_argument("--plan-id", type=int, required=True)
    add_phase.add_argument("--title", required=True)
    add_phase.add_argument("--detail", required=True)
    add_phase.set_defaults(func=cmd_add_phase)

    insert_phase = sub.add_parser("insert-phase", help="insert a todo phase before or after another todo phase")
    insert_phase.add_argument("--plan-id", type=int, required=True)
    insert_phase.add_argument("--title", required=True)
    insert_phase.add_argument("--detail", required=True)
    insert_phase.add_argument("--before-phase-id", type=int)
    insert_phase.add_argument("--after-phase-id", type=int)
    insert_phase.set_defaults(func=cmd_insert_phase)

    move_phase = sub.add_parser("move-phase", help="move a todo phase within the todo section")
    move_phase.add_argument("--phase-id", type=int, required=True)
    move_phase.add_argument("--before-phase-id", type=int)
    move_phase.add_argument("--after-phase-id", type=int)
    move_phase.set_defaults(func=cmd_move_phase)

    update_phase = sub.add_parser("update-phase", help="update a phase")
    update_phase.add_argument("--phase-id", type=int, required=True)
    update_phase.add_argument("--title")
    update_phase.add_argument("--detail")
    update_phase.add_argument("--patch", help='JSON object, e.g. \'{"title":"New title","detail":"Updated text"}\'')
    update_phase.set_defaults(func=cmd_update_phase)

    start_phase = sub.add_parser("start-phase", help="start the first todo phase")
    start_phase.add_argument("--phase-id", type=int, required=True)
    start_phase.set_defaults(func=cmd_start_phase)

    complete_phase = sub.add_parser("complete-phase", help="complete an in_progress phase")
    complete_phase.add_argument("--phase-id", type=int, required=True)
    complete_phase.set_defaults(func=cmd_complete_phase)

    archive_phase = sub.add_parser("archive-phase", help="archive a phase")
    archive_phase.add_argument("--phase-id", type=int, required=True)
    archive_phase.set_defaults(func=cmd_archive_phase)

    export_markdown = sub.add_parser("export-markdown", help="export a plan as markdown")
    export_markdown.add_argument("--plan-id", type=int, required=True)
    export_markdown.set_defaults(func=cmd_export_markdown)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    store = PlanStore(resolve_db_path(getattr(args, "db", None)))
    store.ensure_schema()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
