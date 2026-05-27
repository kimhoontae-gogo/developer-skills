#!/usr/bin/env python3
"""SQLite-backed workflow store and CLI."""

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
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workflows (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK (status IN ('active', 'archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT NULL
);

CREATE TABLE IF NOT EXISTS workflow_stages (
    id INTEGER PRIMARY KEY,
    workflow_id INTEGER NOT NULL REFERENCES workflows(id) ON DELETE RESTRICT,
    position INTEGER NOT NULL,
    title TEXT NOT NULL,
    detail TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('todo', 'in_progress', 'done', 'archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT NULL,
    UNIQUE (workflow_id, position)
);

CREATE TABLE IF NOT EXISTS stage_checklists (
    id INTEGER PRIMARY KEY,
    stage_id INTEGER NOT NULL REFERENCES workflow_stages(id) ON DELETE RESTRICT,
    position INTEGER NOT NULL,
    item TEXT NOT NULL,
    required INTEGER NOT NULL DEFAULT 1 CHECK (required IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (stage_id, position)
);

CREATE TABLE IF NOT EXISTS workflow_runs (
    id INTEGER PRIMARY KEY,
    workflow_id INTEGER NOT NULL UNIQUE REFERENCES workflows(id) ON DELETE RESTRICT,
    current_stage_id INTEGER NULL REFERENCES workflow_stages(id) ON DELETE SET NULL,
    status TEXT NOT NULL CHECK (status IN ('not_started', 'in_progress', 'completed', 'archived')),
    started_at TEXT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT NULL
);

CREATE TABLE IF NOT EXISTS workflow_events (
    id INTEGER PRIMARY KEY,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('project', 'workflow', 'stage', 'checklist', 'run')),
    entity_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_projects_name ON projects(name);
CREATE INDEX IF NOT EXISTS idx_workflows_project_status ON workflows(project_id, status);
CREATE INDEX IF NOT EXISTS idx_workflow_stages_workflow_position ON workflow_stages(workflow_id, position);
CREATE INDEX IF NOT EXISTS idx_stage_checklists_stage_position ON stage_checklists(stage_id, position);
CREATE INDEX IF NOT EXISTS idx_workflow_events_entity ON workflow_events(entity_type, entity_id, created_at);
"""


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return None if row is None else dict(row)


@dataclass(frozen=True)
class WorkflowDetail:
    project: dict[str, Any]
    workflow: dict[str, Any]
    stages: list[dict[str, Any]]
    run: dict[str, Any] | None


class WorkflowStore:
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
            INSERT INTO workflow_events (entity_type, entity_id, event_type, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (entity_type, entity_id, event_type, json.dumps(payload, ensure_ascii=True, sort_keys=True), utc_now()),
        )

    def _project_key(self) -> str:
        return Path.cwd().name

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

    def _get_workflow(self, conn: sqlite3.Connection, workflow_id: int) -> dict[str, Any]:
        row = conn.execute("SELECT * FROM workflows WHERE id = ?", (workflow_id,)).fetchone()
        workflow = row_to_dict(row)
        if workflow is None:
            raise ValueError("workflow not found")
        return workflow

    def _get_stage(self, conn: sqlite3.Connection, stage_id: int) -> dict[str, Any]:
        row = conn.execute("SELECT * FROM workflow_stages WHERE id = ?", (stage_id,)).fetchone()
        stage = row_to_dict(row)
        if stage is None:
            raise ValueError("stage not found")
        return stage

    def _get_run(self, conn: sqlite3.Connection, workflow_id: int) -> dict[str, Any] | None:
        return row_to_dict(conn.execute("SELECT * FROM workflow_runs WHERE workflow_id = ?", (workflow_id,)).fetchone())

    def _get_workflow_for_project(self, conn: sqlite3.Connection, project_id: int) -> dict[str, Any]:
        row = conn.execute(
            """
            SELECT * FROM workflows
            WHERE project_id = ? AND archived_at IS NULL
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (project_id,),
        ).fetchone()
        workflow = row_to_dict(row)
        if workflow is None:
            raise ValueError("workflow not found for project")
        return workflow

    def _workflow_stages(self, conn: sqlite3.Connection, workflow_id: int, *, include_archived: bool = False) -> list[dict[str, Any]]:
        query = "SELECT * FROM workflow_stages WHERE workflow_id = ?"
        params: list[Any] = [workflow_id]
        if not include_archived:
            query += " AND archived_at IS NULL"
        query += " ORDER BY position ASC, id ASC"
        return [dict(row) for row in conn.execute(query, params).fetchall()]

    def _stage_checklists(self, conn: sqlite3.Connection, stage_id: int) -> list[dict[str, Any]]:
        return [dict(row) for row in conn.execute(
            "SELECT * FROM stage_checklists WHERE stage_id = ? ORDER BY position ASC, id ASC",
            (stage_id,),
        ).fetchall()]

    def _replace_checklists(self, conn: sqlite3.Connection, stage_id: int, checklists: Iterable[dict[str, Any]]) -> None:
        now = utc_now()
        conn.execute("DELETE FROM stage_checklists WHERE stage_id = ?", (stage_id,))
        for position, item in enumerate(checklists, start=1):
            conn.execute(
                """
                INSERT INTO stage_checklists (stage_id, position, item, required, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (stage_id, position, item["item"], 1 if item.get("required", True) else 0, now, now),
            )

    def _workflow_events(self, conn: sqlite3.Connection, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = conn.execute(
            "SELECT * FROM workflow_events ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        events: list[dict[str, Any]] = []
        for row in rows:
            event = dict(row)
            try:
                event["payload"] = json.loads(event.pop("payload_json"))
            except json.JSONDecodeError:
                event["payload"] = {}
            events.append(event)
        return events

    def _rewrite_order(self, conn: sqlite3.Connection, workflow_id: int, ordered_stage_ids: Sequence[int]) -> None:
        now = utc_now()
        conn.execute(
            "UPDATE workflow_stages SET position = position + 1000000, updated_at = ? WHERE workflow_id = ? AND archived_at IS NULL",
            (now, workflow_id),
        )
        for index, stage_id in enumerate(ordered_stage_ids, start=1):
            conn.execute("UPDATE workflow_stages SET position = ?, updated_at = ? WHERE id = ?", (index, utc_now(), stage_id))

    def _ensure_run(self, conn: sqlite3.Connection, workflow_id: int) -> dict[str, Any]:
        run = self._get_run(conn, workflow_id)
        if run is not None:
            return run
        now = utc_now()
        cursor = conn.execute(
            """
            INSERT INTO workflow_runs (workflow_id, current_stage_id, status, started_at, updated_at, completed_at)
            VALUES (?, NULL, 'not_started', NULL, ?, NULL)
            """,
            (workflow_id, now),
        )
        return self._get_run(conn, workflow_id) or {"id": cursor.lastrowid, "workflow_id": workflow_id}

    def _current_stage(self, conn: sqlite3.Connection, workflow_id: int) -> dict[str, Any] | None:
        run = self._ensure_run(conn, workflow_id)
        if run["current_stage_id"] is None:
            return None
        return self._get_stage(conn, run["current_stage_id"])

    def _next_stage(self, conn: sqlite3.Connection, workflow_id: int, current_stage_id: int | None) -> dict[str, Any] | None:
        stages = self._workflow_stages(conn, workflow_id)
        if not stages:
            return None
        if current_stage_id is None:
            return stages[0]
        ids = [stage["id"] for stage in stages]
        if current_stage_id not in ids:
            raise ValueError("current stage no longer exists in active workflow stages")
        index = ids.index(current_stage_id)
        return stages[index + 1] if index + 1 < len(stages) else None

    def _update_run_pointer(
        self,
        conn: sqlite3.Connection,
        workflow_id: int,
        *,
        current_stage_id: int | None,
        status: str,
        event_type: str,
        payload: dict[str, Any],
        completed: bool = False,
    ) -> dict[str, Any]:
        run = self._ensure_run(conn, workflow_id)
        now = utc_now()
        conn.execute(
            """
            UPDATE workflow_runs
            SET current_stage_id = ?, status = ?, started_at = COALESCE(started_at, ?), updated_at = ?, completed_at = ?
            WHERE workflow_id = ?
            """,
            (current_stage_id, status, now, now, now if completed else None, workflow_id),
        )
        updated = self._get_run(conn, workflow_id)
        self._event(conn, "run", run["id"], event_type, payload)
        return updated or run

    def create_project(self, name: str, description: str = "") -> dict[str, Any]:
        with self.connect() as conn:
            now = utc_now()
            cursor = conn.execute(
                """
                INSERT INTO projects (name, description, created_at, updated_at)
                VALUES (?, ?, ?, ?)
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
            if not updates:
                return project
            updates.append("updated_at = ?")
            params.append(utc_now())
            params.append(project_id)
            conn.execute(f"UPDATE projects SET {', '.join(updates)} WHERE id = ?", params)
            updated = self._get_project(conn, project_id=project_id)
            self._event(
                conn,
                "project",
                project_id,
                "update",
                {k: v for k, v in {"name": name, "description": description}.items() if v is not None},
            )
            return updated

    def list_projects(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM projects ORDER BY id ASC").fetchall()]

    def show_project(self, project_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            project = self._get_project(conn, project_id=project_id)
            workflows = [dict(row) for row in conn.execute(
                "SELECT * FROM workflows WHERE project_id = ? ORDER BY id ASC",
                (project_id,),
            ).fetchall()]
            return {"project": project, "workflows": workflows}

    def remove_project(self, project_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            project = self._get_project(conn, project_id=project_id)
            workflow_rows = conn.execute("SELECT id FROM workflows WHERE project_id = ?", (project_id,)).fetchall()
            workflow_ids = [int(row["id"]) for row in workflow_rows]
            stage_ids: list[int] = []
            run_ids: list[int] = []
            if workflow_ids:
                placeholders = ",".join("?" for _ in workflow_ids)
                stage_rows = conn.execute(
                    f"SELECT id FROM workflow_stages WHERE workflow_id IN ({placeholders})",
                    workflow_ids,
                ).fetchall()
                stage_ids = [int(row["id"]) for row in stage_rows]
                run_rows = conn.execute(
                    f"SELECT id FROM workflow_runs WHERE workflow_id IN ({placeholders})",
                    workflow_ids,
                ).fetchall()
                run_ids = [int(row["id"]) for row in run_rows]
                if stage_ids:
                    stage_placeholders = ",".join("?" for _ in stage_ids)
                    conn.execute(f"DELETE FROM stage_checklists WHERE stage_id IN ({stage_placeholders})", stage_ids)
                    conn.execute(f"DELETE FROM workflow_events WHERE entity_type = 'stage' AND entity_id IN ({stage_placeholders})", stage_ids)
                if run_ids:
                    run_placeholders = ",".join("?" for _ in run_ids)
                    conn.execute(f"DELETE FROM workflow_events WHERE entity_type = 'run' AND entity_id IN ({run_placeholders})", run_ids)
                conn.execute(f"DELETE FROM workflow_events WHERE entity_type = 'workflow' AND entity_id IN ({placeholders})", workflow_ids)
                conn.execute(f"DELETE FROM workflow_stages WHERE workflow_id IN ({placeholders})", workflow_ids)
                conn.execute(f"DELETE FROM workflow_runs WHERE workflow_id IN ({placeholders})", workflow_ids)
                conn.execute(f"DELETE FROM workflows WHERE id IN ({placeholders})", workflow_ids)
            conn.execute("DELETE FROM workflow_events WHERE entity_type = 'project' AND entity_id = ?", (project_id,))
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            self._event(conn, "project", project_id, "remove", {"project_id": project_id, "workflow_ids": workflow_ids})
            return project

    def resolve_project(self, conn: sqlite3.Connection, project_id: int | None = None, name: str | None = None) -> dict[str, Any]:
        if project_id is not None or name is not None:
            return self._get_project(conn, project_id=project_id, name=name)
        return self._get_project(conn, name=self._project_key())

    def resolve_workflow(
        self,
        conn: sqlite3.Connection,
        *,
        workflow_id: int | None = None,
        project_id: int | None = None,
        project_name: str | None = None,
    ) -> dict[str, Any]:
        if workflow_id is not None:
            return self._get_workflow(conn, workflow_id)
        project = self.resolve_project(conn, project_id=project_id, name=project_name)
        return self._get_workflow_for_project(conn, project["id"])

    def create_workflow(self, project_id: int, title: str, description: str = "") -> dict[str, Any]:
        with self.connect() as conn:
            self._get_project(conn, project_id=project_id)
            now = utc_now()
            cursor = conn.execute(
                """
                INSERT INTO workflows (project_id, title, description, status, created_at, updated_at)
                VALUES (?, ?, ?, 'active', ?, ?)
                """,
                (project_id, title, description, now, now),
            )
            workflow = self._get_workflow(conn, cursor.lastrowid)
            self._ensure_run(conn, workflow["id"])
            self._event(conn, "workflow", workflow["id"], "create", {"project_id": project_id, "title": title})
            return workflow

    def update_workflow(
        self,
        workflow_id: int,
        *,
        title: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        with self.connect() as conn:
            workflow = self._get_workflow(conn, workflow_id)
            if workflow["archived_at"] is not None:
                raise ValueError("cannot update an archived workflow")
            updates: list[str] = []
            params: list[Any] = []
            if title is not None:
                updates.append("title = ?")
                params.append(title)
            if description is not None:
                updates.append("description = ?")
                params.append(description)
            if not updates:
                return workflow
            updates.append("updated_at = ?")
            params.append(utc_now())
            params.append(workflow_id)
            conn.execute(f"UPDATE workflows SET {', '.join(updates)} WHERE id = ?", params)
            updated = self._get_workflow(conn, workflow_id)
            self._event(
                conn,
                "workflow",
                workflow_id,
                "update",
                {k: v for k, v in {"title": title, "description": description}.items() if v is not None},
            )
            return updated

    def remove_workflow(self, workflow_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            workflow = self._get_workflow(conn, workflow_id)
            stage_rows = conn.execute("SELECT id FROM workflow_stages WHERE workflow_id = ?", (workflow_id,)).fetchall()
            stage_ids = [int(row["id"]) for row in stage_rows]
            run_row = conn.execute("SELECT id FROM workflow_runs WHERE workflow_id = ?", (workflow_id,)).fetchone()
            run_id = None if run_row is None else int(run_row["id"])
            if stage_ids:
                placeholders = ",".join("?" for _ in stage_ids)
                conn.execute(f"DELETE FROM stage_checklists WHERE stage_id IN ({placeholders})", stage_ids)
                conn.execute(f"DELETE FROM workflow_events WHERE entity_type = 'stage' AND entity_id IN ({placeholders})", stage_ids)
            conn.execute("DELETE FROM workflow_events WHERE entity_type = 'run' AND entity_id = ?", (run_id if run_id is not None else -1,))
            conn.execute("DELETE FROM workflow_events WHERE entity_type = 'workflow' AND entity_id = ?", (workflow_id,))
            conn.execute("DELETE FROM workflow_runs WHERE workflow_id = ?", (workflow_id,))
            conn.execute("DELETE FROM workflow_stages WHERE workflow_id = ?", (workflow_id,))
            conn.execute("DELETE FROM workflows WHERE id = ?", (workflow_id,))
            self._event(conn, "workflow", workflow_id, "remove", {"workflow_id": workflow_id, "stage_ids": stage_ids, "run_id": run_id})
            return workflow

    def add_stage(self, workflow_id: int, title: str, detail: str, checklists: Iterable[dict[str, Any]] | None = None) -> dict[str, Any]:
        with self.connect() as conn:
            workflow = self._get_workflow(conn, workflow_id)
            stages = self._workflow_stages(conn, workflow_id)
            now = utc_now()
            cursor = conn.execute(
                """
                INSERT INTO workflow_stages (workflow_id, position, title, detail, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'todo', ?, ?)
                """,
                (workflow_id, len(stages) + 1, title, detail, now, now),
            )
            stage = self._get_stage(conn, cursor.lastrowid)
            if checklists:
                self._replace_checklists(conn, stage["id"], checklists)
            self._event(conn, "stage", stage["id"], "create", {"workflow_id": workflow_id, "title": title})
            return stage

    def update_stage(
        self,
        stage_id: int,
        *,
        title: str | None = None,
        detail: str | None = None,
        checklists: Iterable[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        with self.connect() as conn:
            stage = self._get_stage(conn, stage_id)
            checklist_items = list(checklists) if checklists is not None else None
            updates: list[str] = []
            params: list[Any] = []
            if title is not None:
                updates.append("title = ?")
                params.append(title)
            if detail is not None:
                updates.append("detail = ?")
                params.append(detail)
            if updates:
                updates.append("updated_at = ?")
                params.append(utc_now())
                params.append(stage_id)
                conn.execute(f"UPDATE workflow_stages SET {', '.join(updates)} WHERE id = ?", params)
            if checklist_items is not None:
                self._replace_checklists(conn, stage_id, checklist_items)
            updated = self._get_stage(conn, stage_id)
            self._event(
                conn,
                "stage",
                stage_id,
                "update",
                {
                    k: v
                    for k, v in {"title": title, "detail": detail, "checklist_count": None if checklist_items is None else len(checklist_items)}.items()
                    if v is not None
                },
            )
            return updated

    def remove_stage(self, stage_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            stage = self._get_stage(conn, stage_id)
            workflow_id = stage["workflow_id"]
            stages = self._workflow_stages(conn, workflow_id)
            ids = [item["id"] for item in stages]
            if stage_id not in ids:
                raise ValueError("stage not found in workflow")
            index = ids.index(stage_id)
            remaining_ids = [item_id for item_id in ids if item_id != stage_id]
            run = self._get_run(conn, workflow_id)
            current_stage_id = run["current_stage_id"] if run else None
            replacement_stage_id: int | None = None
            if current_stage_id == stage_id:
                if index < len(remaining_ids):
                    replacement_stage_id = remaining_ids[index]
                elif remaining_ids:
                    replacement_stage_id = remaining_ids[-1]
            conn.execute("DELETE FROM stage_checklists WHERE stage_id = ?", (stage_id,))
            conn.execute("DELETE FROM workflow_stages WHERE id = ?", (stage_id,))
            if remaining_ids:
                self._rewrite_order(conn, workflow_id, remaining_ids)
            if current_stage_id == stage_id:
                now = utc_now()
                conn.execute(
                    """
                    UPDATE workflow_runs
                    SET current_stage_id = ?, status = ?, started_at = COALESCE(started_at, ?), updated_at = ?, completed_at = ?
                    WHERE workflow_id = ?
                    """,
                    (
                        replacement_stage_id,
                        "completed" if replacement_stage_id is None else "in_progress",
                        now,
                        now,
                        now if replacement_stage_id is None else None,
                        workflow_id,
                    ),
                )
                self._event(
                    conn,
                    "run",
                    run["id"] if run else workflow_id,
                    "remove-stage",
                    {"workflow_id": workflow_id, "removed_stage_id": stage_id, "current_stage_id": replacement_stage_id},
                )
            self._event(conn, "stage", stage_id, "remove", {"workflow_id": workflow_id, "title": stage["title"]})
            return stage

    def move_stage(
        self,
        stage_id: int,
        *,
        before_stage_id: int | None = None,
        after_stage_id: int | None = None,
    ) -> list[dict[str, Any]]:
        if (before_stage_id is None) == (after_stage_id is None):
            raise ValueError("specify exactly one of before_stage_id or after_stage_id")
        with self.connect() as conn:
            stage = self._get_stage(conn, stage_id)
            workflow_id = stage["workflow_id"]
            stages = self._workflow_stages(conn, workflow_id)
            if stage["archived_at"] is not None:
                raise ValueError("cannot move an archived stage")
            target_id = before_stage_id if before_stage_id is not None else after_stage_id
            target = next((item for item in stages if item["id"] == target_id), None)
            if target is None:
                raise ValueError("target stage not found")
            if target["workflow_id"] != workflow_id:
                raise ValueError("target stage must belong to the same workflow")
            if target["id"] == stage_id:
                raise ValueError("cannot move a stage relative to itself")
            ordered_ids = [item["id"] for item in stages if item["id"] != stage_id]
            target_index = ordered_ids.index(target_id)
            insert_index = target_index if before_stage_id is not None else target_index + 1
            ordered_ids.insert(insert_index, stage_id)
            self._rewrite_order(conn, workflow_id, ordered_ids)
            self._event(
                conn,
                "stage",
                stage_id,
                "move",
                {"workflow_id": workflow_id, "before_stage_id": before_stage_id, "after_stage_id": after_stage_id},
            )
            return self._workflow_stages(conn, workflow_id)

    def set_stage_order(self, workflow_id: int, ordered_stage_ids: Sequence[int]) -> list[dict[str, Any]]:
        with self.connect() as conn:
            workflow = self._get_workflow(conn, workflow_id)
            if workflow["archived_at"] is not None:
                raise ValueError("cannot modify an archived workflow")

            stages = self._workflow_stages(conn, workflow_id, include_archived=False)
            stage_ids = {stage["id"] for stage in stages}

            for stage_id in ordered_stage_ids:
                if stage_id not in stage_ids:
                    raise ValueError(f"stage #{stage_id} not found in workflow")

            if set(ordered_stage_ids) != stage_ids:
                raise ValueError("ordered_stage_ids must include exactly all active stages")

            self._rewrite_order(conn, workflow_id, ordered_stage_ids)
            self._event(
                conn,
                "stage",
                0,
                "set_order",
                {"workflow_id": workflow_id, "ordered_stage_ids": list(ordered_stage_ids)},
            )
            return self._workflow_stages(conn, workflow_id)

    def show_workflow_detail(self, workflow_id: int) -> WorkflowDetail:
        with self.connect() as conn:
            workflow = self._get_workflow(conn, workflow_id)
            project = self._get_project(conn, project_id=workflow["project_id"])
            stages = self._workflow_stages(conn, workflow_id)
            run = self._get_run(conn, workflow_id)
            return WorkflowDetail(project=project, workflow=workflow, stages=stages, run=run)

    def show_stage(self, stage_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            stage = self._get_stage(conn, stage_id)
            workflow = self._get_workflow(conn, stage["workflow_id"])
            project = self._get_project(conn, project_id=workflow["project_id"])
            checklists = self._stage_checklists(conn, stage_id)
            return {"project": project, "workflow": workflow, "stage": stage, "checklists": checklists}

    def get_current(self, workflow_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            run = self._ensure_run(conn, workflow_id)
            stage = None if run["current_stage_id"] is None else self._get_stage(conn, run["current_stage_id"])
            return {"run": run, "stage": stage}

    def get_checklist(self, workflow_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            run = self._ensure_run(conn, workflow_id)
            if run["current_stage_id"] is None:
                return {"run": run, "stage": None, "checklists": []}
            stage = self._get_stage(conn, run["current_stage_id"])
            return {"run": run, "stage": stage, "checklists": self._stage_checklists(conn, stage["id"])}

    def get_next(self, workflow_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            run = self._ensure_run(conn, workflow_id)
            next_stage = self._next_stage(conn, workflow_id, run["current_stage_id"])
            return {"run": run, "stage": next_stage}

    def move(self, workflow_id: int, stage_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            self._get_workflow(conn, workflow_id)
            stage = self._get_stage(conn, stage_id)
            if stage["workflow_id"] != workflow_id:
                raise ValueError("stage must belong to the workflow")
            run = self._ensure_run(conn, workflow_id)
            return self._update_run_pointer(
                conn,
                workflow_id,
                current_stage_id=stage_id,
                status="in_progress",
                event_type="move",
                payload={"workflow_id": workflow_id, "from_stage_id": run["current_stage_id"], "to_stage_id": stage_id},
                completed=False,
            )

    def status(self, workflow_id: int) -> dict[str, Any]:
        with self.connect() as conn:
            workflow = self._get_workflow(conn, workflow_id)
            project = self._get_project(conn, project_id=workflow["project_id"])
            run = self._ensure_run(conn, workflow_id)
            stages = self._workflow_stages(conn, workflow_id)
            current_stage = None if run["current_stage_id"] is None else self._get_stage(conn, run["current_stage_id"])
            next_stage = self._next_stage(conn, workflow_id, run["current_stage_id"])
            checklists = [] if current_stage is None else self._stage_checklists(conn, current_stage["id"])
            if current_stage is None:
                completed_count = 0
            else:
                completed_count = max(0, [stage["id"] for stage in stages].index(current_stage["id"]))
            return {
                "project": project,
                "workflow": workflow,
                "run": run,
                "current_stage": current_stage,
                "next_stage": next_stage,
                "total_stages": len(stages),
                "completed_stages": completed_count,
                "remaining_stages": max(0, len(stages) - completed_count - (0 if current_stage is None else 1)),
                "current_checklists": checklists,
            }

    def history(self, workflow_id: int, *, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as conn:
            run = self._ensure_run(conn, workflow_id)
            events = []
            for event in self._workflow_events(conn, limit=limit * 5):
                payload = event.get("payload", {})
                if event["entity_type"] == "workflow" and event["entity_id"] == workflow_id:
                    events.append(event)
                elif payload.get("workflow_id") == workflow_id:
                    events.append(event)
                elif event["entity_type"] == "run" and event["entity_id"] == run["id"]:
                    events.append(event)
                if len(events) >= limit:
                    break
            return events

    def list_workflows(self, project_id: int | None = None) -> list[dict[str, Any]]:
        with self.connect() as conn:
            query = "SELECT * FROM workflows"
            params: list[Any] = []
            if project_id is not None:
                query += " WHERE project_id = ?"
                params.append(project_id)
            query += " ORDER BY id ASC"
            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def list_stages(self, workflow_id: int) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return self._workflow_stages(conn, workflow_id)


def resolve_db_path(value: str | None) -> Path:
    if value:
        return Path(value)
    env = os.environ.get("WORKFLOW_DB_PATH")
    if env:
        return Path(env)
    return Path.home() / ".developer-skills" / "workflow.sqlite3"


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))


def _print_workflow_detail(detail: WorkflowDetail) -> None:
    current_stage = None
    if detail.run and detail.run["current_stage_id"] is not None:
        current_stage = next((stage for stage in detail.stages if stage["id"] == detail.run["current_stage_id"]), None)
    print(f"Project: {detail.project['name']} (#{detail.project['id']})")
    print(f"Workflow: {detail.workflow['title']} (#{detail.workflow['id']})")
    print(f"Description: {detail.workflow['description']}")
    print(f"Status: {detail.workflow['status']}")
    print(f"Current stage: {current_stage['title']} (#{current_stage['id']})" if current_stage else "Current stage: None")
    print("Stages:")
    for stage in detail.stages:
        print(f"  - [{stage['position']}] {stage['title']} #{stage['id']} :: {stage['status']}")


def _print_stage_detail(payload: dict[str, Any]) -> None:
    project = payload["project"]
    workflow = payload["workflow"]
    stage = payload["stage"]
    checklists = payload["checklists"]
    print(f"Project: {project['name']} (#{project['id']})")
    print(f"Workflow: {workflow['title']} (#{workflow['id']})")
    print(f"Stage: {stage['title']} (#{stage['id']})")
    print(f"Position: {stage['position']}")
    print(f"Status: {stage['status']}")
    print(f"Detail: {stage['detail']}")
    if checklists:
        print("Checklist:")
        for item in checklists:
            marker = "[required]" if item["required"] else "[optional]"
            print(f"  {marker} {item['position']}. {item['item']}")


def _print_status(payload: dict[str, Any]) -> None:
    project = payload["project"]
    workflow = payload["workflow"]
    run = payload["run"]
    current_stage = payload["current_stage"]
    next_stage = payload["next_stage"]
    print(f"Project: {project['name']} (#{project['id']})")
    print(f"Workflow: {workflow['title']} (#{workflow['id']})")
    print(f"Run status: {run['status']}")
    print(f"Current stage: {current_stage['title']} (#{current_stage['id']})" if current_stage else "Current stage: None")
    print(f"Next stage: {next_stage['title']} (#{next_stage['id']})" if next_stage else "Next stage: None")
    print(f"Total stages: {payload['total_stages']}")
    print(f"Completed stages: {payload['completed_stages']}")
    print(f"Remaining stages: {payload['remaining_stages']}")
    if payload["current_checklists"]:
        print("Current checklist:")
        for item in payload["current_checklists"]:
            marker = "[required]" if item["required"] else "[optional]"
            print(f"  {marker} {item['position']}. {item['item']}")


def _print_history(events: list[dict[str, Any]]) -> None:
    for event in events:
        print(f"{event['created_at']} {event['entity_type']}#{event['entity_id']} {event['event_type']} {event['payload']}")


def _parse_json_object(value: str) -> dict[str, Any]:
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("expected a JSON object")
    return payload


def _checklist_payloads(values: Iterable[str] | None) -> list[dict[str, Any]]:
    if not values:
        return []
    payloads: list[dict[str, Any]] = []
    for raw in values:
        payload = _parse_json_object(raw)
        item = payload.get("item")
        if not isinstance(item, str):
            raise ValueError('checklist JSON must include string field "item"')
        payloads.append({"item": item, "required": bool(payload.get("required", True))})
    return payloads


def cmd_init_db(args: argparse.Namespace) -> None:
    store = WorkflowStore(resolve_db_path(args.db))
    store.ensure_schema()
    print(str(store.db_path))


def cmd_create_project(args: argparse.Namespace) -> None:
    store = WorkflowStore(resolve_db_path(args.db))
    with store.connect() as conn:
        name = args.name or store._project_key()
    _print_json(store.create_project(name, args.description or ""))


def cmd_update_project(args: argparse.Namespace) -> None:
    store = WorkflowStore(resolve_db_path(args.db))
    _print_json(store.update_project(args.project_id, name=args.name, description=args.description))


def cmd_list_projects(args: argparse.Namespace) -> None:
    store = WorkflowStore(resolve_db_path(args.db))
    _print_json(store.list_projects())


def cmd_show_project(args: argparse.Namespace) -> None:
    store = WorkflowStore(resolve_db_path(args.db))
    _print_json(store.show_project(args.project_id))


def cmd_remove_project(args: argparse.Namespace) -> None:
    store = WorkflowStore(resolve_db_path(args.db))
    _print_json(store.remove_project(args.project_id))


def cmd_create_workflow(args: argparse.Namespace) -> None:
    store = WorkflowStore(resolve_db_path(args.db))
    with store.connect() as conn:
        project = store.resolve_project(conn, project_id=args.project_id, name=args.project_name)
    _print_json(store.create_workflow(project["id"], args.title, args.description or ""))


def cmd_update_workflow(args: argparse.Namespace) -> None:
    store = WorkflowStore(resolve_db_path(args.db))
    with store.connect() as conn:
        workflow = store.resolve_workflow(conn, workflow_id=args.workflow_id, project_id=args.project_id, project_name=args.project_name)
    _print_json(store.update_workflow(workflow["id"], title=args.title, description=args.description))


def cmd_remove_workflow(args: argparse.Namespace) -> None:
    store = WorkflowStore(resolve_db_path(args.db))
    with store.connect() as conn:
        workflow = store.resolve_workflow(conn, workflow_id=args.workflow_id, project_id=args.project_id, project_name=args.project_name)
    _print_json(store.remove_workflow(workflow["id"]))


def cmd_add_stage(args: argparse.Namespace) -> None:
    store = WorkflowStore(resolve_db_path(args.db))
    checklists = _checklist_payloads(args.checklist)
    _print_json(store.add_stage(args.workflow_id, args.title, args.detail, checklists=checklists or None))


def cmd_update_stage(args: argparse.Namespace) -> None:
    store = WorkflowStore(resolve_db_path(args.db))
    checklists = _checklist_payloads(args.checklist) if args.checklist is not None else None
    _print_json(store.update_stage(args.stage_id, title=args.title, detail=args.detail, checklists=checklists))


def cmd_remove_stage(args: argparse.Namespace) -> None:
    store = WorkflowStore(resolve_db_path(args.db))
    _print_json(store.remove_stage(args.stage_id))


def cmd_move_stage(args: argparse.Namespace) -> None:
    store = WorkflowStore(resolve_db_path(args.db))
    _print_json(
        store.move_stage(
            args.stage_id,
            before_stage_id=args.before_stage_id,
            after_stage_id=args.after_stage_id,
        )
    )


def cmd_set_stage_order(args: argparse.Namespace) -> None:
    store = WorkflowStore(resolve_db_path(args.db))
    _print_json(store.set_stage_order(args.workflow_id, args.stage_ids))


def cmd_show_workflow(args: argparse.Namespace) -> None:
    store = WorkflowStore(resolve_db_path(args.db))
    with store.connect() as conn:
        workflow = store.resolve_workflow(conn, workflow_id=args.workflow_id, project_id=args.project_id, project_name=args.project_name)
    detail = store.show_workflow_detail(workflow["id"])
    if args.json:
        _print_json({"project": detail.project, "workflow": detail.workflow, "stages": detail.stages, "run": detail.run})
    else:
        _print_workflow_detail(detail)


def cmd_show_stage(args: argparse.Namespace) -> None:
    store = WorkflowStore(resolve_db_path(args.db))
    payload = store.show_stage(args.stage_id)
    if args.json:
        _print_json(payload)
    else:
        _print_stage_detail(payload)


def cmd_get_current(args: argparse.Namespace) -> None:
    store = WorkflowStore(resolve_db_path(args.db))
    with store.connect() as conn:
        workflow = store.resolve_workflow(conn, workflow_id=args.workflow_id, project_id=args.project_id, project_name=args.project_name)
    _print_json(store.get_current(workflow["id"]))


def cmd_get_checklist(args: argparse.Namespace) -> None:
    store = WorkflowStore(resolve_db_path(args.db))
    with store.connect() as conn:
        workflow = store.resolve_workflow(conn, workflow_id=args.workflow_id, project_id=args.project_id, project_name=args.project_name)
    _print_json(store.get_checklist(workflow["id"]))


def cmd_get_next(args: argparse.Namespace) -> None:
    store = WorkflowStore(resolve_db_path(args.db))
    with store.connect() as conn:
        workflow = store.resolve_workflow(conn, workflow_id=args.workflow_id, project_id=args.project_id, project_name=args.project_name)
    _print_json(store.get_next(workflow["id"]))


def cmd_move(args: argparse.Namespace) -> None:
    store = WorkflowStore(resolve_db_path(args.db))
    with store.connect() as conn:
        workflow = store.resolve_workflow(conn, workflow_id=args.workflow_id, project_id=args.project_id, project_name=args.project_name)
    _print_json(store.move(workflow["id"], args.stage_id))


def cmd_list_workflows(args: argparse.Namespace) -> None:
    store = WorkflowStore(resolve_db_path(args.db))
    with store.connect() as conn:
        project = store.resolve_project(conn, project_id=args.project_id, name=args.project_name)
    _print_json(store.list_workflows(project_id=project["id"]))


def cmd_list_stages(args: argparse.Namespace) -> None:
    store = WorkflowStore(resolve_db_path(args.db))
    with store.connect() as conn:
        workflow = store.resolve_workflow(conn, workflow_id=args.workflow_id, project_id=args.project_id, project_name=args.project_name)
    _print_json(store.list_stages(workflow["id"]))


def cmd_status(args: argparse.Namespace) -> None:
    store = WorkflowStore(resolve_db_path(args.db))
    with store.connect() as conn:
        workflow = store.resolve_workflow(conn, workflow_id=args.workflow_id, project_id=args.project_id, project_name=args.project_name)
    payload = store.status(workflow["id"])
    if args.json:
        _print_json(payload)
    else:
        _print_status(payload)


def cmd_history(args: argparse.Namespace) -> None:
    store = WorkflowStore(resolve_db_path(args.db))
    with store.connect() as conn:
        workflow = store.resolve_workflow(conn, workflow_id=args.workflow_id, project_id=args.project_id, project_name=args.project_name)
    events = store.history(workflow["id"], limit=args.limit)
    if args.json:
        _print_json(events)
    else:
        _print_history(events)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SQLite store utilities for workflow")
    parser.add_argument("--db", help="SQLite database path")
    sub = parser.add_subparsers(dest="command", required=True)

    init_db = sub.add_parser("init-db", help="create or migrate the database schema")
    init_db.set_defaults(func=cmd_init_db)

    create_project = sub.add_parser("create-project", help="create a project")
    create_project.add_argument("--name")
    create_project.add_argument("--description")
    create_project.set_defaults(func=cmd_create_project)

    update_project = sub.add_parser("update-project", help="update a project name or description")
    update_project.add_argument("--project-id", type=int, required=True)
    update_project.add_argument("--name")
    update_project.add_argument("--description")
    update_project.set_defaults(func=cmd_update_project)

    list_projects = sub.add_parser("list-projects", help="list projects")
    list_projects.set_defaults(func=cmd_list_projects)

    show_project = sub.add_parser("show-project", help="show a project detail view")
    show_project.add_argument("--project-id", type=int, required=True)
    show_project.set_defaults(func=cmd_show_project)

    remove_project = sub.add_parser("remove-project", help="remove a project and its workflows")
    remove_project.add_argument("--project-id", type=int, required=True)
    remove_project.set_defaults(func=cmd_remove_project)

    create_workflow = sub.add_parser("create-workflow", help="create a workflow")
    create_workflow.add_argument("--project-id", type=int)
    create_workflow.add_argument("--project-name")
    create_workflow.add_argument("--title", required=True)
    create_workflow.add_argument("--description")
    create_workflow.set_defaults(func=cmd_create_workflow)

    update_workflow = sub.add_parser("update-workflow", help="update a workflow title or description")
    update_workflow.add_argument("--workflow-id", type=int)
    update_workflow.add_argument("--project-id", type=int)
    update_workflow.add_argument("--project-name")
    update_workflow.add_argument("--title")
    update_workflow.add_argument("--description")
    update_workflow.set_defaults(func=cmd_update_workflow)

    remove_workflow = sub.add_parser("remove-workflow", help="remove a workflow and its stages")
    remove_workflow.add_argument("--workflow-id", type=int)
    remove_workflow.add_argument("--project-id", type=int)
    remove_workflow.add_argument("--project-name")
    remove_workflow.set_defaults(func=cmd_remove_workflow)

    list_workflows = sub.add_parser("list-workflows", help="list workflows")
    list_workflows.add_argument("--project-id", type=int)
    list_workflows.add_argument("--project-name")
    list_workflows.set_defaults(func=cmd_list_workflows)

    add_stage = sub.add_parser("add-stage", help="append a stage to a workflow")
    add_stage.add_argument("--workflow-id", type=int, required=True)
    add_stage.add_argument("--title", required=True)
    add_stage.add_argument("--detail", required=True)
    add_stage.add_argument("--checklist", action="append", help='checklist JSON object, e.g. \'{"item":"run unit tests","required":true}\'')
    add_stage.set_defaults(func=cmd_add_stage)

    update_stage = sub.add_parser("update-stage", help="update a stage definition")
    update_stage.add_argument("--stage-id", type=int, required=True)
    update_stage.add_argument("--title")
    update_stage.add_argument("--detail")
    update_stage.add_argument("--checklist", action="append", help='checklist JSON object, e.g. \'{"item":"run unit tests","required":true}\'')
    update_stage.set_defaults(func=cmd_update_stage)

    remove_stage = sub.add_parser("remove-stage", help="remove a stage from a workflow")
    remove_stage.add_argument("--stage-id", type=int, required=True)
    remove_stage.set_defaults(func=cmd_remove_stage)

    move_stage = sub.add_parser("move-stage", help="reorder a stage within a workflow")
    move_stage.add_argument("--stage-id", type=int, required=True)
    move_stage.add_argument("--before-stage-id", type=int)
    move_stage.add_argument("--after-stage-id", type=int)
    move_stage.set_defaults(func=cmd_move_stage)

    set_stage_order = sub.add_parser("set-stage-order", help="set the order of all active stages at once by listing their IDs")
    set_stage_order.add_argument("--workflow-id", type=int, required=True)
    set_stage_order.add_argument("--stage-ids", type=int, nargs="+", required=True, help="ordered list of stage IDs")
    set_stage_order.set_defaults(func=cmd_set_stage_order)

    list_stages = sub.add_parser("list-stages", help="list stages in a workflow")
    list_stages.add_argument("--workflow-id", type=int)
    list_stages.add_argument("--project-id", type=int)
    list_stages.add_argument("--project-name")
    list_stages.set_defaults(func=cmd_list_stages)

    show_workflow = sub.add_parser("show-workflow", help="show a workflow detail view")
    show_workflow.add_argument("--workflow-id", type=int)
    show_workflow.add_argument("--project-id", type=int)
    show_workflow.add_argument("--project-name")
    show_workflow.add_argument("--json", action="store_true", help="output JSON instead of human-readable text")
    show_workflow.set_defaults(func=cmd_show_workflow)

    show_stage = sub.add_parser("show-stage", help="show a stage detail view")
    show_stage.add_argument("--stage-id", type=int, required=True)
    show_stage.add_argument("--json", action="store_true", help="output JSON instead of human-readable text")
    show_stage.set_defaults(func=cmd_show_stage)

    get_current = sub.add_parser("get-current", help="show the current stage")
    get_current.add_argument("--workflow-id", type=int)
    get_current.add_argument("--project-id", type=int)
    get_current.add_argument("--project-name")
    get_current.set_defaults(func=cmd_get_current)

    get_checklist = sub.add_parser("get-checklist", help="show the current stage checklist")
    get_checklist.add_argument("--workflow-id", type=int)
    get_checklist.add_argument("--project-id", type=int)
    get_checklist.add_argument("--project-name")
    get_checklist.set_defaults(func=cmd_get_checklist)

    get_next = sub.add_parser("get-next", help="show the next stage")
    get_next.add_argument("--workflow-id", type=int)
    get_next.add_argument("--project-id", type=int)
    get_next.add_argument("--project-name")
    get_next.set_defaults(func=cmd_get_next)

    move = sub.add_parser("move", help="move the runtime pointer to a stage")
    move.add_argument("--workflow-id", type=int)
    move.add_argument("--project-id", type=int)
    move.add_argument("--project-name")
    move.add_argument("--stage-id", type=int, required=True)
    move.set_defaults(func=cmd_move)

    status = sub.add_parser("status", help="show workflow status")
    status.add_argument("--workflow-id", type=int)
    status.add_argument("--project-id", type=int)
    status.add_argument("--project-name")
    status.add_argument("--json", action="store_true", help="output JSON instead of human-readable text")
    status.set_defaults(func=cmd_status)

    history = sub.add_parser("history", help="show workflow event history")
    history.add_argument("--workflow-id", type=int)
    history.add_argument("--project-id", type=int)
    history.add_argument("--project-name")
    history.add_argument("--limit", type=int, default=20)
    history.add_argument("--json", action="store_true", help="output JSON instead of human-readable text")
    history.set_defaults(func=cmd_history)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    store = WorkflowStore(resolve_db_path(getattr(args, "db", None)))
    store.ensure_schema()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
