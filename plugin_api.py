"""Project Explorer Dashboard Plugin — Backend API Routes.

Mounted at /api/plugins/project-explorer/ by the dashboard plugin system.

All storage and logic is self-contained within this plugin - no core file modifications.
"""

import json
import os
import sqlite3
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

DEFAULT_EXCLUDES = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next", "target"}

HERMES_HOME = Path.home() / ".hermes"


class ProjectStore:
    """SQLite-backed project storage for tracking projects discovered from sessions."""

    PROJECTS_SQL = """
    CREATE TABLE IF NOT EXISTS projects (
        id TEXT PRIMARY KEY,
        path TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        first_seen REAL NOT NULL,
        last_used REAL NOT NULL,
        session_count INTEGER DEFAULT 1,
        is_git_repo INTEGER DEFAULT 0,
        git_remote TEXT,
        tags TEXT DEFAULT '[]'
    );
    CREATE INDEX IF NOT EXISTS idx_projects_last_used ON projects(last_used DESC);
    CREATE INDEX IF NOT EXISTS idx_projects_path ON projects(path);
    """

    def __init__(self):
        self.db_path = HERMES_HOME / "projects.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self):
        self._conn.executescript(self.PROJECTS_SQL)
        self._conn.commit()

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def list_projects(self) -> List[Dict[str, Any]]:
        cursor = self._conn.execute(
            "SELECT * FROM projects ORDER BY last_used DESC"
        )
        rows = cursor.fetchall()
        projects = []
        for row in rows:
            p = dict(row)
            p["is_git_repo"] = bool(p["is_git_repo"])
            p["tags"] = json.loads(p["tags"]) if p["tags"] else []
            projects.append(p)
        return projects

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        cursor = self._conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        row = cursor.fetchone()
        if not row:
            return None
        p = dict(row)
        p["is_git_repo"] = bool(p["is_git_repo"])
        p["tags"] = json.loads(p["tags"]) if p["tags"] else []
        return p

    def get_project_by_path(self, path: str) -> Optional[Dict[str, Any]]:
        cursor = self._conn.execute("SELECT * FROM projects WHERE path = ?", (path,))
        row = cursor.fetchone()
        if not row:
            return None
        p = dict(row)
        p["is_git_repo"] = bool(p["is_git_repo"])
        p["tags"] = json.loads(p["tags"]) if p["tags"] else []
        return p

    def add_project(self, path: str) -> Dict[str, Any]:
        project_path = Path(path).resolve()
        if not project_path.exists():
            raise ValueError(f"Path does not exist: {path}")

        name = project_path.name
        is_git_repo = (project_path / ".git").exists()
        git_remote = None

        if is_git_repo:
            git_config = project_path / ".git" / "config"
            if git_config.exists():
                try:
                    content = git_config.read_text()
                    for line in content.split("\n"):
                        if line.strip().startswith("url = "):
                            git_remote = line.strip().replace("url = ", "")
                            break
                except Exception:
                    pass

        now = time.time()
        project_id = str(uuid.uuid4())

        self._conn.execute(
            """INSERT OR REPLACE INTO projects
               (id, path, name, first_seen, last_used, session_count, is_git_repo, git_remote)
               VALUES (?, ?, ?, ?, ?, 1, ?, ?)""",
            (project_id, str(project_path), name, now, now, is_git_repo, git_remote),
        )
        self._conn.commit()

        return self.get_project(project_id)

    def update_project(self, project_id: str, **kwargs) -> None:
        allowed = {"tags", "session_count"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}

        if not updates:
            return

        if "tags" in updates:
            updates["tags"] = json.dumps(updates["tags"])

        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [project_id]

        self._conn.execute(f"UPDATE projects SET {set_clause} WHERE id = ?", values)
        self._conn.commit()

    def touch_project(self, project_id: str) -> None:
        now = time.time()
        self._conn.execute(
            "UPDATE projects SET last_used = ?, session_count = session_count + 1 WHERE id = ?",
            (now, project_id),
        )
        self._conn.commit()

    def delete_project(self, project_id: str) -> None:
        self._conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        self._conn.commit()

    def maybe_add_project(self, path: str) -> Optional[Dict[str, Any]]:
        """Add project if not exists, or update last_used if exists."""
        existing = self.get_project_by_path(path)
        if existing:
            self.touch_project(existing["id"])
            return existing
        try:
            return self.add_project(path)
        except Exception:
            return None


def build_tree(
    root_path: str,
    max_depth: int = 5,
    include: Optional[List[str]] = None,
    exclude: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Recursively build directory tree."""
    root = Path(root_path).resolve()
    if not root.exists() or not root.is_dir():
        return None

    exclude_set = set(exclude) | DEFAULT_EXCLUDES if exclude else DEFAULT_EXCLUDES

    def walk(dir_path: Path, current_depth: int) -> Optional[Dict[str, Any]]:
        if current_depth >= max_depth:
            return None

        children = []
        try:
            for entry in sorted(dir_path.iterdir()):
                if entry.name in exclude_set or entry.name.startswith("."):
                    continue

                if entry.is_dir():
                    child = walk(entry, current_depth + 1)
                    if child:
                        children.append(child)
                else:
                    if include and not any(entry.match(p) for p in include):
                        continue

                    try:
                        stat = entry.stat()
                        children.append(
                            {
                                "name": entry.name,
                                "type": "file",
                                "size": stat.st_size,
                                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            }
                        )
                    except (OSError, PermissionError):
                        continue
        except PermissionError:
            return None

        return {
            "name": dir_path.name,
            "type": "directory",
            "path": str(dir_path),
            "children": children,
        }

    return walk(root, 0)


def normalize_to_project_root(path: str) -> Optional[str]:
    """Walk up from path to find project root (git root or first directory with common project files)."""
    if not path:
        return None

    p = Path(path).resolve()
    if not p.exists():
        return None

    if p.is_file():
        p = p.parent

    project_markers = {".git", "package.json", "Cargo.toml", "pyproject.toml", "go.mod", "Makefile", "requirements.txt", "setup.py"}

    for parent in [p] + list(p.parents):
        if any((parent / marker).exists() for marker in project_markers):
            return str(parent)

    if p.is_dir() and any((p / f).exists() for f in ["src", "lib", "app"]):
        return str(p)

    return None


def get_store() -> ProjectStore:
    return ProjectStore()


class AddProjectRequest(BaseModel):
    path: str


class UpdateTagsRequest(BaseModel):
    tags: list[str]


class LinkProjectRequest(BaseModel):
    project_path: str


@router.get("/sessions")
async def get_active_sessions():
    """Get sessions - now handled by frontend via SDK.api.getSessions(). Kept for compatibility."""
    return {"sessions": [], "note": "Frontend now fetches via SDK.api.getSessions()"}


@router.post("/sessions/{session_id}/link")
async def link_session_to_project(session_id: str, body: LinkProjectRequest):
    """Link a session to a project by path."""
    project_root = normalize_to_project_root(body.project_path)
    
    if not project_root:
        project_root = body.project_path
    
    store = get_store()
    try:
        project = store.maybe_add_project(project_root)
        if not project:
            raise HTTPException(status_code=500, detail="Failed to add project")
        return {"project": project, "session_id": session_id}
    finally:
        store.close()


@router.get("/projects")
async def list_projects():
    """List all tracked projects."""
    store = get_store()
    try:
        projects = store.list_projects()
        return {"projects": projects}
    finally:
        store.close()


@router.post("/projects")
async def add_project(body: AddProjectRequest):
    """Manually add a project."""
    store = get_store()
    try:
        project = store.add_project(body.path)
        return {"project": project}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        store.close()


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    """Remove a project from tracking."""
    store = get_store()
    try:
        store.delete_project(project_id)
        return {"ok": True}
    finally:
        store.close()


@router.get("/projects/{project_id}")
async def get_project(project_id: str):
    """Get a single project by ID."""
    store = get_store()
    try:
        project = store.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return {"project": project}
    finally:
        store.close()


@router.put("/projects/{project_id}/tags")
async def update_tags(project_id: str, body: UpdateTagsRequest):
    """Update project tags."""
    store = get_store()
    try:
        store.update_project(project_id, tags=body.tags)
        project = store.get_project(project_id)
        return {"project": project}
    finally:
        store.close()


@router.get("/projects/{project_id}/tree")
async def get_tree(project_id: str, depth: int = 5):
    """Get file tree for a project."""
    store = get_store()
    try:
        project = store.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        tree = build_tree(
            root_path=project["path"],
            max_depth=depth,
            exclude=list(DEFAULT_EXCLUDES),
        )

        if tree is None:
            raise HTTPException(status_code=404, detail="Project path not accessible")

        return {"tree": tree, "project": project}
    finally:
        store.close()


@router.post("/projects/{project_id}/refresh")
async def refresh_project(project_id: str):
    """Re-scan project for changes (update git remote, etc.)."""
    store = get_store()
    try:
        project = store.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        project_path = Path(project["path"])
        is_git_repo = (project_path / ".git").exists()
        git_remote = None

        if is_git_repo:
            git_config = project_path / ".git" / "config"
            if git_config.exists():
                try:
                    content = git_config.read_text()
                    for line in content.split("\n"):
                        if line.strip().startswith("url = "):
                            git_remote = line.strip().replace("url = ", "")
                            break
                except Exception:
                    pass

        store._conn.execute(
            "UPDATE projects SET is_git_repo = ?, git_remote = ?, last_used = ? WHERE id = ?",
            (is_git_repo, git_remote, time.time(), project_id),
        )
        store._conn.commit()

        project = store.get_project(project_id)
        return {"project": project}
    finally:
        store.close()


@router.get("/discover")
async def discover_from_session():
    """Discover project from current session's terminal.cwd."""
    cwd = os.getenv("TERMINAL_CWD", os.getcwd())
    project_root = normalize_to_project_root(cwd)

    if not project_root:
        return {"discovered": False, "cwd": cwd}

    store = get_store()
    try:
        project = store.maybe_add_project(project_root)
        return {"discovered": True, "project": project, "cwd": cwd}
    finally:
        store.close()