#!/usr/bin/env python3
"""JSON-backed workflow store and CLI for project-local workflow definitions."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

SCHEMA_VERSION = 1
DEFAULT_PROJECT_DIRNAME = ".workflow"
DEFINITION_FILENAME = "definition.json"
RUNTIME_FILENAME = "runtime.json"
GITIGNORE_FILENAME = ".gitignore"


def utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _project_root(value: str | os.PathLike[str] | None) -> Path:
    return Path(value or os.getcwd()).expanduser().resolve()


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object in {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
    os.replace(tmp_path, path)


def _ensure_list(value: Any, *, name: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"expected list for {name}")
    return value


def _project_summary(root: Path, definition: dict[str, Any]) -> dict[str, Any]:
    project = definition["project"]
    return {
        "path": str(root),
        "project_dir": str(root / DEFAULT_PROJECT_DIRNAME),
        "name": project["name"],
        "description": project["description"],
        "created_at": project["created_at"],
        "updated_at": project["updated_at"],
        "workflow_count": len(definition["workflows"]),
    }


def _workflow_summary(workflow: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": workflow["id"],
        "title": workflow["title"],
        "description": workflow["description"],
        "status": workflow["status"],
        "created_at": workflow["created_at"],
        "updated_at": workflow["updated_at"],
        "archived_at": workflow.get("archived_at"),
        "stage_count": len(workflow.get("stages", [])),
    }


def _stage_summary(stage: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": stage["id"],
        "workflow_id": stage["workflow_id"],
        "position": stage["position"],
        "title": stage["title"],
        "detail": stage["detail"],
        "status": stage["status"],
        "created_at": stage["created_at"],
        "updated_at": stage["updated_at"],
        "archived_at": stage.get("archived_at"),
        "checklist_count": len(stage.get("checklists", [])),
    }


@dataclass(frozen=True)
class WorkflowDetail:
    project: dict[str, Any]
    workflow: dict[str, Any]
    stages: list[dict[str, Any]]
    run: dict[str, Any] | None


class WorkflowJSONStore:
    def __init__(self, project_root: str | os.PathLike[str]):
        self.project_root = _project_root(project_root)
        self.project_dir = self.project_root / DEFAULT_PROJECT_DIRNAME
        self.definition_path = self.project_dir / DEFINITION_FILENAME
        self.runtime_path = self.project_dir / RUNTIME_FILENAME
        self.gitignore_path = self.project_root / GITIGNORE_FILENAME

    # ------------------------------------------------------------------
    # File helpers
    # ------------------------------------------------------------------

    def _ensure_gitignore(self) -> None:
        self.project_root.mkdir(parents=True, exist_ok=True)
        existing = ""
        if self.gitignore_path.exists():
            existing = self.gitignore_path.read_text(encoding="utf-8")
        required_lines = [f"{DEFAULT_PROJECT_DIRNAME}/{RUNTIME_FILENAME}", f"{DEFAULT_PROJECT_DIRNAME}/*.tmp"]
        lines = [line.rstrip() for line in existing.splitlines() if line.strip()]
        changed = False
        for item in required_lines:
            if item not in lines:
                lines.append(item)
                changed = True
        if changed or not self.gitignore_path.exists():
            self.gitignore_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _cleanup_gitignore(self) -> None:
        if not self.gitignore_path.exists():
            return
        entries_to_remove = {
            f"{DEFAULT_PROJECT_DIRNAME}/{RUNTIME_FILENAME}",
            f"{DEFAULT_PROJECT_DIRNAME}/*.tmp",
        }
        lines = [line.rstrip() for line in self.gitignore_path.read_text(encoding="utf-8").splitlines()]
        remaining = [line for line in lines if line.strip() and line not in entries_to_remove]
        if remaining:
            self.gitignore_path.write_text("\n".join(remaining) + "\n", encoding="utf-8")
        else:
            self.gitignore_path.unlink()

    def _default_definition(self, name: str, description: str) -> dict[str, Any]:
        now = utc_now()
        return {
            "schema_version": SCHEMA_VERSION,
            "project": {
                "name": name,
                "description": description,
                "created_at": now,
                "updated_at": now,
            },
            "next_ids": {
                "workflow": 1,
                "stage": 1,
                "checklist": 1,
            },
            "workflows": [],
        }

    def _default_runtime(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "next_event_id": 1,
            "runs": {},
            "events": [],
        }

    def _load_definition(self, *, required: bool = True) -> dict[str, Any] | None:
        raw = _read_json(self.definition_path)
        if raw is None:
            if required:
                raise ValueError("project is not initialized")
            return None
        return self._normalize_definition(raw)

    def _load_runtime(self) -> dict[str, Any]:
        raw = _read_json(self.runtime_path)
        if raw is None:
            return self._default_runtime()
        return self._normalize_runtime(raw)

    def _save_definition(self, definition: dict[str, Any]) -> None:
        _write_json(self.definition_path, definition)

    def _save_runtime(self, runtime: dict[str, Any]) -> None:
        _write_json(self.runtime_path, runtime)

    def _normalize_definition(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload.setdefault("schema_version", SCHEMA_VERSION)
        project = payload.setdefault("project", {})
        project.setdefault("name", self.project_root.name)
        project.setdefault("description", "")
        project.setdefault("created_at", utc_now())
        project.setdefault("updated_at", project["created_at"])
        next_ids = payload.setdefault("next_ids", {})
        next_ids.setdefault("workflow", 1)
        next_ids.setdefault("stage", 1)
        next_ids.setdefault("checklist", 1)
        workflows = _ensure_list(payload.get("workflows"), name="workflows")
        normalized_workflows: list[dict[str, Any]] = []
        for workflow in workflows:
            if not isinstance(workflow, dict):
                raise ValueError("workflow entries must be objects")
            workflow = dict(workflow)
            workflow.setdefault("status", "active")
            workflow.setdefault("description", "")
            workflow.setdefault("created_at", utc_now())
            workflow.setdefault("updated_at", workflow["created_at"])
            workflow.setdefault("archived_at", None)
            stages = _ensure_list(workflow.get("stages"), name="stages")
            normalized_stages: list[dict[str, Any]] = []
            for stage in stages:
                if not isinstance(stage, dict):
                    raise ValueError("stage entries must be objects")
                stage = dict(stage)
                stage.setdefault("status", "todo")
                stage.setdefault("detail", "")
                stage.setdefault("created_at", utc_now())
                stage.setdefault("updated_at", stage["created_at"])
                stage.setdefault("archived_at", None)
                checklists = _ensure_list(stage.get("checklists"), name="checklists")
                normalized_checklists: list[dict[str, Any]] = []
                for checklist in checklists:
                    if not isinstance(checklist, dict):
                        raise ValueError("checklist entries must be objects")
                    checklist = dict(checklist)
                    checklist.setdefault("required", True)
                    checklist.setdefault("created_at", utc_now())
                    checklist.setdefault("updated_at", checklist["created_at"])
                    normalized_checklists.append(checklist)
                stage["checklists"] = normalized_checklists
                normalized_stages.append(stage)
            workflow["stages"] = normalized_stages
            normalized_workflows.append(workflow)
        payload["workflows"] = normalized_workflows
        return payload

    def _normalize_runtime(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload.setdefault("schema_version", SCHEMA_VERSION)
        payload.setdefault("next_event_id", 1)
        runs = payload.setdefault("runs", {})
        if not isinstance(runs, dict):
            raise ValueError("runtime runs must be a JSON object")
        events = _ensure_list(payload.get("events"), name="events")
        normalized_events: list[dict[str, Any]] = []
        for event in events:
            if not isinstance(event, dict):
                raise ValueError("runtime events must be objects")
            event = dict(event)
            event.setdefault("payload", {})
            normalized_events.append(event)
        payload["events"] = normalized_events
        return payload

    def _ensure_initialized(self) -> dict[str, Any]:
        definition = self._load_definition(required=True)
        assert definition is not None
        return definition

    def _save_project_assets(self, definition: dict[str, Any], runtime: dict[str, Any] | None = None) -> None:
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_gitignore()
        self._save_definition(definition)
        if runtime is not None:
            self._save_runtime(runtime)

    # ------------------------------------------------------------------
    # Entity lookup helpers
    # ------------------------------------------------------------------

    def _workflow_list(self, definition: dict[str, Any]) -> list[dict[str, Any]]:
        workflows = definition["workflows"]
        return sorted(workflows, key=lambda item: (item["updated_at"], item["id"]))

    def _workflow_by_id(self, definition: dict[str, Any], workflow_id: int) -> dict[str, Any]:
        for workflow in definition["workflows"]:
            if int(workflow["id"]) == int(workflow_id):
                return workflow
        raise ValueError("workflow not found")

    def _workflow_index(self, definition: dict[str, Any], workflow_id: int) -> int:
        for index, workflow in enumerate(definition["workflows"]):
            if int(workflow["id"]) == int(workflow_id):
                return index
        raise ValueError("workflow not found")

    def _stage_lookup(self, definition: dict[str, Any], stage_id: int) -> tuple[dict[str, Any], dict[str, Any], int, int]:
        for workflow_index, workflow in enumerate(definition["workflows"]):
            for stage_index, stage in enumerate(workflow["stages"]):
                if int(stage["id"]) == int(stage_id):
                    return workflow, stage, workflow_index, stage_index
        raise ValueError("stage not found")

    def _resolve_workflow(
        self,
        definition: dict[str, Any],
        workflow_id: int | None = None,
    ) -> dict[str, Any]:
        if workflow_id is not None:
            return self._workflow_by_id(definition, workflow_id)
        active = [workflow for workflow in definition["workflows"] if workflow.get("status", "active") == "active"]
        if not active:
            raise ValueError("workflow not found")
        return sorted(active, key=lambda item: (item["updated_at"], item["id"]))[-1]

    def _resolve_workflow_for_stage(self, definition: dict[str, Any], stage_id: int) -> dict[str, Any]:
        workflow, _, _, _ = self._stage_lookup(definition, stage_id)
        return workflow

    def _stage_checklists(self, stage: dict[str, Any]) -> list[dict[str, Any]]:
        return sorted(stage.get("checklists", []), key=lambda item: (item["position"], item["id"]))

    def _workflow_stages(self, workflow: dict[str, Any]) -> list[dict[str, Any]]:
        return sorted(workflow.get("stages", []), key=lambda item: (item["position"], item["id"]))

    def _ensure_run(self, runtime: dict[str, Any], workflow_id: int) -> dict[str, Any]:
        key = str(int(workflow_id))
        run = runtime["runs"].get(key)
        if run is not None:
            return run
        now = utc_now()
        run = {
            "id": int(workflow_id),
            "workflow_id": int(workflow_id),
            "current_stage_id": None,
            "status": "not_started",
            "started_at": None,
            "updated_at": now,
            "completed_at": None,
        }
        runtime["runs"][key] = run
        return run

    def _append_event(
        self,
        runtime: dict[str, Any],
        *,
        entity_type: str,
        entity_id: int,
        event_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        event = {
            "id": int(runtime["next_event_id"]),
            "entity_type": entity_type,
            "entity_id": int(entity_id),
            "event_type": event_type,
            "payload": payload,
            "created_at": utc_now(),
        }
        runtime["next_event_id"] += 1
        runtime["events"].append(event)
        return event

    def _sorted_events(self, runtime: dict[str, Any], workflow_id: int, limit: int) -> list[dict[str, Any]]:
        events = []
        for event in sorted(runtime["events"], key=lambda item: item["id"], reverse=True):
            payload = event.get("payload") or {}
            if event["entity_type"] == "workflow" and event["entity_id"] == workflow_id:
                events.append(event)
            elif event["entity_type"] == "run" and int(payload.get("workflow_id", -1)) == int(workflow_id):
                events.append(event)
            elif int(payload.get("workflow_id", -1)) == int(workflow_id):
                events.append(event)
            if len(events) >= limit:
                break
        return events

    def _rewrite_positions(self, workflow: dict[str, Any]) -> None:
        for index, stage in enumerate(workflow.get("stages", []), start=1):
            stage["position"] = index

    # ------------------------------------------------------------------
    # Project operations
    # ------------------------------------------------------------------

    def create_project(self, name: str | None = None, description: str = "") -> dict[str, Any]:
        if self.definition_path.exists():
            return self.show_project()
        project_name = name or self.project_root.name
        definition = self._default_definition(project_name, description)
        runtime = self._default_runtime()
        self._save_project_assets(definition, runtime)
        return self.show_project()

    def update_project(self, *, name: str | None = None, description: str | None = None) -> dict[str, Any]:
        definition = self._ensure_initialized()
        project = definition["project"]
        changed = False
        if name is not None:
            project["name"] = name
            changed = True
        if description is not None:
            project["description"] = description
            changed = True
        if changed:
            project["updated_at"] = utc_now()
            self._save_definition(definition)
        return self.show_project()

    def list_projects(self) -> list[dict[str, Any]]:
        if not self.definition_path.exists():
            return []
        definition = self._ensure_initialized()
        return [_project_summary(self.project_root, definition)]

    def show_project(self) -> dict[str, Any]:
        definition = self._ensure_initialized()
        runtime = self._load_runtime()
        workflows = []
        for workflow in self._workflow_list(definition):
            run = runtime["runs"].get(str(workflow["id"]))
            workflows.append(
                {
                    "workflow": _workflow_summary(workflow),
                    "run": None if run is None else dict(run),
                    "stage_count": len(workflow.get("stages", [])),
                }
            )
        return {"project": _project_summary(self.project_root, definition), "workflows": workflows}

    def remove_project(self) -> dict[str, Any]:
        definition = self._ensure_initialized()
        summary = _project_summary(self.project_root, definition)
        if self.project_dir.exists():
            shutil.rmtree(self.project_dir)
        self._cleanup_gitignore()
        return summary

    # ------------------------------------------------------------------
    # Workflow operations
    # ------------------------------------------------------------------

    def create_workflow(self, title: str, description: str = "") -> dict[str, Any]:
        definition = self._ensure_initialized()
        runtime = self._load_runtime()
        now = utc_now()
        workflow_id = int(definition["next_ids"]["workflow"])
        definition["next_ids"]["workflow"] += 1
        workflow = {
            "id": workflow_id,
            "title": title,
            "description": description,
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "archived_at": None,
            "stages": [],
        }
        definition["workflows"].append(workflow)
        self._ensure_run(runtime, workflow_id)
        self._append_event(runtime, entity_type="workflow", entity_id=workflow_id, event_type="create", payload={"title": title})
        self._save_project_assets(definition, runtime)
        return workflow

    def update_workflow(
        self,
        workflow_id: int | None = None,
        *,
        title: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        definition = self._ensure_initialized()
        runtime = self._load_runtime()
        workflow = self._resolve_workflow(definition, workflow_id)
        if workflow.get("status") != "active":
            raise ValueError("cannot update an archived workflow")
        changed = False
        if title is not None:
            workflow["title"] = title
            changed = True
        if description is not None:
            workflow["description"] = description
            changed = True
        if changed:
            workflow["updated_at"] = utc_now()
            self._append_event(
                runtime,
                entity_type="workflow",
                entity_id=workflow["id"],
                event_type="update",
                payload={k: v for k, v in {"title": title, "description": description}.items() if v is not None},
            )
            self._save_project_assets(definition, runtime)
        return workflow

    def remove_workflow(self, workflow_id: int | None = None) -> dict[str, Any]:
        definition = self._ensure_initialized()
        runtime = self._load_runtime()
        workflow = self._resolve_workflow(definition, workflow_id)
        stages = list(workflow.get("stages", []))
        stage_ids = [int(stage["id"]) for stage in stages]
        definition["workflows"] = [item for item in definition["workflows"] if int(item["id"]) != int(workflow["id"])]
        runtime["runs"].pop(str(workflow["id"]), None)
        runtime["events"] = [
            event
            for event in runtime["events"]
            if not (
                (event["entity_type"] == "workflow" and int(event["entity_id"]) == int(workflow["id"]))
                or (event["entity_type"] == "stage" and int(event["entity_id"]) in stage_ids)
                or (event["entity_type"] == "run" and int((event.get("payload") or {}).get("workflow_id", -1)) == int(workflow["id"]))
            )
        ]
        self._save_project_assets(definition, runtime)
        return workflow

    def list_workflows(self) -> list[dict[str, Any]]:
        definition = self._ensure_initialized()
        return [_workflow_summary(workflow) for workflow in self._workflow_list(definition)]

    def show_workflow_detail(self, workflow_id: int | None = None) -> WorkflowDetail:
        definition = self._ensure_initialized()
        runtime = self._load_runtime()
        workflow = self._resolve_workflow(definition, workflow_id)
        run = runtime["runs"].get(str(workflow["id"]))
        return WorkflowDetail(
            project=_project_summary(self.project_root, definition),
            workflow=_workflow_summary(workflow),
            stages=[_stage_summary(stage) for stage in self._workflow_stages(workflow)],
            run=None if run is None else dict(run),
        )

    # ------------------------------------------------------------------
    # Stage operations
    # ------------------------------------------------------------------

    def add_stage(
        self,
        workflow_id: int | None,
        title: str,
        detail: str,
        *,
        checklists: Iterable[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        definition = self._ensure_initialized()
        runtime = self._load_runtime()
        workflow = self._resolve_workflow(definition, workflow_id)
        now = utc_now()
        stage_id = int(definition["next_ids"]["stage"])
        definition["next_ids"]["stage"] += 1
        stage = {
            "id": stage_id,
            "workflow_id": workflow["id"],
            "position": len(workflow["stages"]) + 1,
            "title": title,
            "detail": detail,
            "status": "todo",
            "created_at": now,
            "updated_at": now,
            "archived_at": None,
            "checklists": [],
        }
        for position, item in enumerate(list(checklists or []), start=1):
            checklist_id = int(definition["next_ids"]["checklist"])
            definition["next_ids"]["checklist"] += 1
            stage["checklists"].append(
                {
                    "id": checklist_id,
                    "stage_id": stage_id,
                    "position": position,
                    "item": item["item"],
                    "required": bool(item.get("required", True)),
                    "created_at": now,
                    "updated_at": now,
                }
            )
        workflow["stages"].append(stage)
        workflow["updated_at"] = now
        self._append_event(
            runtime,
            entity_type="stage",
            entity_id=stage_id,
            event_type="create",
            payload={"workflow_id": workflow["id"], "title": title},
        )
        self._save_project_assets(definition, runtime)
        return stage

    def update_stage(
        self,
        stage_id: int,
        *,
        title: str | None = None,
        detail: str | None = None,
        checklists: Iterable[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        definition = self._ensure_initialized()
        runtime = self._load_runtime()
        workflow, stage, _, _ = self._stage_lookup(definition, stage_id)
        now = utc_now()
        changed = False
        if title is not None:
            stage["title"] = title
            changed = True
        if detail is not None:
            stage["detail"] = detail
            changed = True
        if checklists is not None:
            new_checklists = []
            for position, item in enumerate(list(checklists), start=1):
                checklist_id = int(definition["next_ids"]["checklist"])
                definition["next_ids"]["checklist"] += 1
                new_checklists.append(
                    {
                        "id": checklist_id,
                        "stage_id": stage_id,
                        "position": position,
                        "item": item["item"],
                        "required": bool(item.get("required", True)),
                        "created_at": now,
                        "updated_at": now,
                    }
                )
            stage["checklists"] = new_checklists
            changed = True
        if changed:
            stage["updated_at"] = now
            workflow["updated_at"] = now
            self._append_event(
                runtime,
                entity_type="stage",
                entity_id=stage_id,
                event_type="update",
                payload={
                    k: v
                    for k, v in {
                        "title": title,
                        "detail": detail,
                        "checklist_count": None if checklists is None else len(stage["checklists"]),
                    }.items()
                    if v is not None
                },
            )
            self._save_project_assets(definition, runtime)
        return stage

    def remove_stage(self, stage_id: int) -> dict[str, Any]:
        definition = self._ensure_initialized()
        runtime = self._load_runtime()
        workflow, stage, workflow_index, stage_index = self._stage_lookup(definition, stage_id)
        stages = workflow["stages"]
        current_run = self._ensure_run(runtime, workflow["id"])
        current_stage_id = current_run["current_stage_id"]
        removed_stage = dict(stage)
        stages.pop(stage_index)
        self._rewrite_positions(workflow)
        replacement_stage_id: int | None = None
        if current_stage_id == stage_id:
            if stage_index < len(stages):
                replacement_stage_id = stages[stage_index]["id"]
            elif stages:
                replacement_stage_id = stages[-1]["id"]
            now = utc_now()
            current_run["current_stage_id"] = replacement_stage_id
            current_run["status"] = "completed" if replacement_stage_id is None else "in_progress"
            current_run["updated_at"] = now
            current_run["completed_at"] = now if replacement_stage_id is None else None
            self._append_event(
                runtime,
                entity_type="run",
                entity_id=current_run["id"],
                event_type="remove-stage",
                payload={
                    "workflow_id": workflow["id"],
                    "removed_stage_id": stage_id,
                    "current_stage_id": replacement_stage_id,
                },
            )
        workflow["updated_at"] = utc_now()
        self._append_event(
            runtime,
            entity_type="stage",
            entity_id=stage_id,
            event_type="remove",
            payload={"workflow_id": workflow["id"], "title": stage["title"]},
        )
        self._save_project_assets(definition, runtime)
        return removed_stage

    def move_stage(
        self,
        stage_id: int,
        *,
        before_stage_id: int | None = None,
        after_stage_id: int | None = None,
    ) -> list[dict[str, Any]]:
        if (before_stage_id is None) == (after_stage_id is None):
            raise ValueError("specify exactly one of before_stage_id or after_stage_id")
        definition = self._ensure_initialized()
        runtime = self._load_runtime()
        workflow, stage, _, stage_index = self._stage_lookup(definition, stage_id)
        target_id = before_stage_id if before_stage_id is not None else after_stage_id
        assert target_id is not None
        target_workflow, target_stage, _, target_index = self._stage_lookup(definition, target_id)
        if target_workflow["id"] != workflow["id"]:
            raise ValueError("target stage must belong to the same workflow")
        if target_stage["id"] == stage_id:
            raise ValueError("cannot move a stage relative to itself")
        stages = workflow["stages"]
        moving = stages.pop(stage_index)
        if before_stage_id is not None:
            target_index = next(index for index, item in enumerate(stages) if int(item["id"]) == int(before_stage_id))
            stages.insert(target_index, moving)
        else:
            target_index = next(index for index, item in enumerate(stages) if int(item["id"]) == int(after_stage_id))
            stages.insert(target_index + 1, moving)
        self._rewrite_positions(workflow)
        workflow["updated_at"] = utc_now()
        self._append_event(
            runtime,
            entity_type="stage",
            entity_id=stage_id,
            event_type="move",
            payload={"workflow_id": workflow["id"], "before_stage_id": before_stage_id, "after_stage_id": after_stage_id},
        )
        self._save_project_assets(definition, runtime)
        return [dict(item) for item in self._workflow_stages(workflow)]

    def set_stage_order(self, workflow_id: int, ordered_stage_ids: Sequence[int]) -> list[dict[str, Any]]:
        definition = self._ensure_initialized()
        runtime = self._load_runtime()
        workflow = self._resolve_workflow(definition, workflow_id)
        stages = self._workflow_stages(workflow)
        stage_ids = {int(stage["id"]) for stage in stages}
        if set(int(item) for item in ordered_stage_ids) != stage_ids:
            raise ValueError("ordered_stage_ids must include exactly all active stages")
        stage_by_id = {int(stage["id"]): stage for stage in stages}
        workflow["stages"] = [stage_by_id[int(stage_id)] for stage_id in ordered_stage_ids]
        self._rewrite_positions(workflow)
        workflow["updated_at"] = utc_now()
        self._append_event(
            runtime,
            entity_type="stage",
            entity_id=0,
            event_type="set_order",
            payload={"workflow_id": workflow["id"], "ordered_stage_ids": [int(item) for item in ordered_stage_ids]},
        )
        self._save_project_assets(definition, runtime)
        return [dict(item) for item in self._workflow_stages(workflow)]

    def list_stages(self, workflow_id: int | None = None) -> list[dict[str, Any]]:
        definition = self._ensure_initialized()
        workflow = self._resolve_workflow(definition, workflow_id)
        return [_stage_summary(stage) for stage in self._workflow_stages(workflow)]

    def show_stage(self, stage_id: int) -> dict[str, Any]:
        definition = self._ensure_initialized()
        workflow, stage, _, _ = self._stage_lookup(definition, stage_id)
        runtime = self._load_runtime()
        return {
            "project": _project_summary(self.project_root, definition),
            "workflow": _workflow_summary(workflow),
            "stage": _stage_summary(stage),
            "checklists": sorted(stage.get("checklists", []), key=lambda item: (item["position"], item["id"])),
            "run": runtime["runs"].get(str(workflow["id"])),
        }

    # ------------------------------------------------------------------
    # Runtime operations
    # ------------------------------------------------------------------

    def get_current(self, workflow_id: int | None = None) -> dict[str, Any]:
        definition = self._ensure_initialized()
        runtime = self._load_runtime()
        workflow = self._resolve_workflow(definition, workflow_id)
        run = self._ensure_run(runtime, workflow["id"])
        self._save_runtime(runtime)
        stage = None
        if run["current_stage_id"] is not None:
            _, stage, _, _ = self._stage_lookup(definition, run["current_stage_id"])
            stage = _stage_summary(stage)
        return {"run": dict(run), "stage": stage}

    def get_checklist(self, workflow_id: int | None = None) -> dict[str, Any]:
        definition = self._ensure_initialized()
        runtime = self._load_runtime()
        workflow = self._resolve_workflow(definition, workflow_id)
        run = self._ensure_run(runtime, workflow["id"])
        self._save_runtime(runtime)
        if run["current_stage_id"] is None:
            return {"run": dict(run), "stage": None, "checklists": []}
        _, stage, _, _ = self._stage_lookup(definition, run["current_stage_id"])
        return {"run": dict(run), "stage": _stage_summary(stage), "checklists": sorted(stage.get("checklists", []), key=lambda item: (item["position"], item["id"]))}

    def get_next(self, workflow_id: int | None = None) -> dict[str, Any]:
        definition = self._ensure_initialized()
        runtime = self._load_runtime()
        workflow = self._resolve_workflow(definition, workflow_id)
        run = self._ensure_run(runtime, workflow["id"])
        self._save_runtime(runtime)
        stages = self._workflow_stages(workflow)
        if not stages:
            return {"run": dict(run), "stage": None}
        ids = [int(stage["id"]) for stage in stages]
        if run["current_stage_id"] is None:
            return {"run": dict(run), "stage": _stage_summary(stages[0])}
        if int(run["current_stage_id"]) not in ids:
            raise ValueError("current stage no longer exists in active workflow stages")
        index = ids.index(int(run["current_stage_id"]))
        return {"run": dict(run), "stage": None if index + 1 >= len(stages) else _stage_summary(stages[index + 1])}

    def move(self, workflow_id: int | None, stage_id: int) -> dict[str, Any]:
        definition = self._ensure_initialized()
        runtime = self._load_runtime()
        workflow = self._resolve_workflow(definition, workflow_id)
        _, stage, _, _ = self._stage_lookup(definition, stage_id)
        if int(stage["workflow_id"]) != int(workflow["id"]):
            raise ValueError("stage must belong to the workflow")
        run = self._ensure_run(runtime, workflow["id"])
        now = utc_now()
        previous_stage_id = run["current_stage_id"]
        run["current_stage_id"] = int(stage_id)
        run["status"] = "in_progress"
        run["started_at"] = run["started_at"] or now
        run["updated_at"] = now
        run["completed_at"] = None
        self._append_event(
            runtime,
            entity_type="run",
            entity_id=run["id"],
            event_type="move",
            payload={"workflow_id": workflow["id"], "from_stage_id": previous_stage_id, "to_stage_id": stage_id},
        )
        self._save_project_assets(definition, runtime)
        return dict(run)

    def status(self, workflow_id: int | None = None) -> dict[str, Any]:
        definition = self._ensure_initialized()
        runtime = self._load_runtime()
        workflow = self._resolve_workflow(definition, workflow_id)
        run = self._ensure_run(runtime, workflow["id"])
        self._save_runtime(runtime)
        stages = self._workflow_stages(workflow)
        ids = [int(stage["id"]) for stage in stages]
        current_stage = None
        if run["current_stage_id"] is not None:
            _, current_stage_data, _, _ = self._stage_lookup(definition, run["current_stage_id"])
            current_stage = _stage_summary(current_stage_data)
        next_stage = None
        if stages:
            if run["current_stage_id"] is None:
                next_stage = _stage_summary(stages[0])
            elif int(run["current_stage_id"]) in ids:
                index = ids.index(int(run["current_stage_id"]))
                if index + 1 < len(stages):
                    next_stage = _stage_summary(stages[index + 1])
        if run["status"] == "completed":
            completed_count = len(stages)
        elif current_stage is None:
            completed_count = 0
        else:
            completed_count = ids.index(int(run["current_stage_id"]))
        return {
            "project": _project_summary(self.project_root, definition),
            "workflow": _workflow_summary(workflow),
            "run": dict(run),
            "current_stage": current_stage,
            "next_stage": next_stage,
            "total_stages": len(stages),
            "completed_stages": completed_count,
            "remaining_stages": max(0, len(stages) - completed_count - (0 if current_stage is None else 1)),
            "current_checklists": []
            if current_stage is None
            else sorted(
                self._stage_lookup(definition, int(current_stage["id"]))[1].get("checklists", []),
                key=lambda item: (item["position"], item["id"]),
            ),
        }

    def history(self, workflow_id: int | None = None, *, limit: int = 20) -> list[dict[str, Any]]:
        definition = self._ensure_initialized()
        runtime = self._load_runtime()
        workflow = self._resolve_workflow(definition, workflow_id)
        run = self._ensure_run(runtime, workflow["id"])
        self._save_runtime(runtime)
        return self._sorted_events(runtime, workflow["id"], limit)


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))


def _print_workflow_detail(detail: WorkflowDetail) -> None:
    current_stage = None
    if detail.run and detail.run.get("current_stage_id") is not None:
        current_stage = next((stage for stage in detail.stages if int(stage["id"]) == int(detail.run["current_stage_id"])), None)
    print(f"Project: {detail.project['name']} ({detail.project['path']})")
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
    print(f"Project: {project['name']} ({project['path']})")
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
    print(f"Project: {project['name']} ({project['path']})")
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


def cmd_init_project(args: argparse.Namespace) -> None:
    store = WorkflowJSONStore(args.project_path)
    _print_json(store.create_project(args.name, args.description or ""))


def cmd_update_project(args: argparse.Namespace) -> None:
    store = WorkflowJSONStore(args.project_path)
    _print_json(store.update_project(name=args.name, description=args.description))


def cmd_list_projects(args: argparse.Namespace) -> None:
    store = WorkflowJSONStore(args.project_path)
    _print_json(store.list_projects())


def cmd_show_project(args: argparse.Namespace) -> None:
    store = WorkflowJSONStore(args.project_path)
    _print_json(store.show_project())


def cmd_remove_project(args: argparse.Namespace) -> None:
    store = WorkflowJSONStore(args.project_path)
    _print_json(store.remove_project())


def cmd_create_workflow(args: argparse.Namespace) -> None:
    store = WorkflowJSONStore(args.project_path)
    _print_json(store.create_workflow(args.title, args.description or ""))


def cmd_update_workflow(args: argparse.Namespace) -> None:
    store = WorkflowJSONStore(args.project_path)
    _print_json(store.update_workflow(args.workflow_id, title=args.title, description=args.description))


def cmd_remove_workflow(args: argparse.Namespace) -> None:
    store = WorkflowJSONStore(args.project_path)
    _print_json(store.remove_workflow(args.workflow_id))


def cmd_add_stage(args: argparse.Namespace) -> None:
    store = WorkflowJSONStore(args.project_path)
    checklists = _checklist_payloads(args.checklist)
    _print_json(store.add_stage(args.workflow_id, args.title, args.detail, checklists=checklists or None))


def cmd_update_stage(args: argparse.Namespace) -> None:
    store = WorkflowJSONStore(args.project_path)
    checklists = _checklist_payloads(args.checklist) if args.checklist is not None else None
    _print_json(store.update_stage(args.stage_id, title=args.title, detail=args.detail, checklists=checklists))


def cmd_remove_stage(args: argparse.Namespace) -> None:
    store = WorkflowJSONStore(args.project_path)
    _print_json(store.remove_stage(args.stage_id))


def cmd_move_stage(args: argparse.Namespace) -> None:
    store = WorkflowJSONStore(args.project_path)
    _print_json(
        store.move_stage(
            args.stage_id,
            before_stage_id=args.before_stage_id,
            after_stage_id=args.after_stage_id,
        )
    )


def cmd_set_stage_order(args: argparse.Namespace) -> None:
    store = WorkflowJSONStore(args.project_path)
    _print_json(store.set_stage_order(args.workflow_id, args.stage_ids))


def cmd_show_workflow(args: argparse.Namespace) -> None:
    store = WorkflowJSONStore(args.project_path)
    detail = store.show_workflow_detail(args.workflow_id)
    if args.json:
        _print_json({"project": detail.project, "workflow": detail.workflow, "stages": detail.stages, "run": detail.run})
    else:
        _print_workflow_detail(detail)


def cmd_show_stage(args: argparse.Namespace) -> None:
    store = WorkflowJSONStore(args.project_path)
    payload = store.show_stage(args.stage_id)
    if args.json:
        _print_json(payload)
    else:
        _print_stage_detail(payload)


def cmd_get_current(args: argparse.Namespace) -> None:
    store = WorkflowJSONStore(args.project_path)
    _print_json(store.get_current(args.workflow_id))


def cmd_get_checklist(args: argparse.Namespace) -> None:
    store = WorkflowJSONStore(args.project_path)
    _print_json(store.get_checklist(args.workflow_id))


def cmd_get_next(args: argparse.Namespace) -> None:
    store = WorkflowJSONStore(args.project_path)
    _print_json(store.get_next(args.workflow_id))


def cmd_move(args: argparse.Namespace) -> None:
    store = WorkflowJSONStore(args.project_path)
    _print_json(store.move(args.workflow_id, args.stage_id))


def cmd_list_workflows(args: argparse.Namespace) -> None:
    store = WorkflowJSONStore(args.project_path)
    _print_json(store.list_workflows())


def cmd_list_stages(args: argparse.Namespace) -> None:
    store = WorkflowJSONStore(args.project_path)
    _print_json(store.list_stages(args.workflow_id))


def cmd_status(args: argparse.Namespace) -> None:
    store = WorkflowJSONStore(args.project_path)
    payload = store.status(args.workflow_id)
    if args.json:
        _print_json(payload)
    else:
        _print_status(payload)


def cmd_history(args: argparse.Namespace) -> None:
    store = WorkflowJSONStore(args.project_path)
    events = store.history(args.workflow_id, limit=args.limit)
    if args.json:
        _print_json(events)
    else:
        _print_history(events)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="JSON store utilities for workflow")
    parser.add_argument(
        "--project-path",
        default=os.getcwd(),
        help="project root path; defaults to the current working directory",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    init_project = sub.add_parser("create-project", help="initialize the project workflow files")
    init_project.add_argument("--name")
    init_project.add_argument("--description")
    init_project.set_defaults(func=cmd_init_project)

    update_project = sub.add_parser("update-project", help="update the project metadata")
    update_project.add_argument("--name")
    update_project.add_argument("--description")
    update_project.set_defaults(func=cmd_update_project)

    list_projects = sub.add_parser("list-projects", help="list the current project record")
    list_projects.set_defaults(func=cmd_list_projects)

    show_project = sub.add_parser("show-project", help="show the current project detail view")
    show_project.set_defaults(func=cmd_show_project)

    remove_project = sub.add_parser("remove-project", help="remove the project workflow files")
    remove_project.set_defaults(func=cmd_remove_project)

    create_workflow = sub.add_parser("create-workflow", help="create a workflow")
    create_workflow.add_argument("--title", required=True)
    create_workflow.add_argument("--description")
    create_workflow.set_defaults(func=cmd_create_workflow)

    update_workflow = sub.add_parser("update-workflow", help="update a workflow title or description")
    update_workflow.add_argument("--workflow-id", type=int)
    update_workflow.add_argument("--title")
    update_workflow.add_argument("--description")
    update_workflow.set_defaults(func=cmd_update_workflow)

    remove_workflow = sub.add_parser("remove-workflow", help="remove a workflow and its stages")
    remove_workflow.add_argument("--workflow-id", type=int)
    remove_workflow.set_defaults(func=cmd_remove_workflow)

    list_workflows = sub.add_parser("list-workflows", help="list workflows")
    list_workflows.set_defaults(func=cmd_list_workflows)

    add_stage = sub.add_parser("add-stage", help="append a stage to a workflow")
    add_stage.add_argument("--workflow-id", type=int)
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
    set_stage_order.add_argument("--workflow-id", type=int)
    set_stage_order.add_argument("--stage-ids", type=int, nargs="+", required=True, help="ordered list of stage IDs")
    set_stage_order.set_defaults(func=cmd_set_stage_order)

    list_stages = sub.add_parser("list-stages", help="list stages in a workflow")
    list_stages.add_argument("--workflow-id", type=int)
    list_stages.set_defaults(func=cmd_list_stages)

    show_workflow = sub.add_parser("show-workflow", help="show a workflow detail view")
    show_workflow.add_argument("--workflow-id", type=int)
    show_workflow.add_argument("--json", action="store_true", help="output JSON instead of human-readable text")
    show_workflow.set_defaults(func=cmd_show_workflow)

    show_stage = sub.add_parser("show-stage", help="show a stage detail view")
    show_stage.add_argument("--stage-id", type=int, required=True)
    show_stage.add_argument("--json", action="store_true", help="output JSON instead of human-readable text")
    show_stage.set_defaults(func=cmd_show_stage)

    get_current = sub.add_parser("get-current", help="show the current stage")
    get_current.add_argument("--workflow-id", type=int)
    get_current.set_defaults(func=cmd_get_current)

    get_checklist = sub.add_parser("get-checklist", help="show the current stage checklist")
    get_checklist.add_argument("--workflow-id", type=int)
    get_checklist.set_defaults(func=cmd_get_checklist)

    get_next = sub.add_parser("get-next", help="show the next stage")
    get_next.add_argument("--workflow-id", type=int)
    get_next.set_defaults(func=cmd_get_next)

    move = sub.add_parser("move", help="move the runtime pointer to a stage")
    move.add_argument("--workflow-id", type=int)
    move.add_argument("--stage-id", type=int, required=True)
    move.set_defaults(func=cmd_move)

    status = sub.add_parser("status", help="show workflow status")
    status.add_argument("--workflow-id", type=int)
    status.add_argument("--json", action="store_true", help="output JSON instead of human-readable text")
    status.set_defaults(func=cmd_status)

    history = sub.add_parser("history", help="show workflow event history")
    history.add_argument("--workflow-id", type=int)
    history.add_argument("--limit", type=int, default=20)
    history.add_argument("--json", action="store_true", help="output JSON instead of human-readable text")
    history.set_defaults(func=cmd_history)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except Exception as exc:  # pragma: no cover - surfaced via CLI
        parser.error(str(exc))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
