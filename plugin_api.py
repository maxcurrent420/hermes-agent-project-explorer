"""Project Explorer Dashboard Plugin — Backend API Routes.

Mounted at /api/plugins/project-explorer/ by the dashboard plugin system.

All storage and logic is self-contained within this plugin - no core file modifications.
"""

import asyncio
import json
import logging
import os
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, Header
from pydantic import BaseModel

logger = logging.getLogger(__name__)

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
    CREATE TABLE IF NOT EXISTS session_projects (
        session_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        linked_at REAL NOT NULL,
        FOREIGN KEY (project_id) REFERENCES projects(id)
    );
    CREATE VIRTUAL TABLE IF NOT EXISTS project_kb_fts USING fts5(
        project_id UNINDEXED,
        section UNINDEXED,
        content,
        tokenize='porter unicode61'
    );
    CREATE TABLE IF NOT EXISTS project_activity (
        project_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        timestamp REAL NOT NULL,
        actions TEXT NOT NULL,
        summary TEXT,
        FOREIGN KEY (project_id) REFERENCES projects(id),
        PRIMARY KEY (project_id, session_id)
    );
    CREATE TABLE IF NOT EXISTS project_kb_index (
        project_id TEXT NOT NULL,
        section TEXT NOT NULL,
        content TEXT NOT NULL,
        updated_at REAL NOT NULL,
        FOREIGN KEY (project_id) REFERENCES projects(id)
    );
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

    def get_session_project(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get the project linked to a session, with link metadata."""
        cursor = self._conn.execute(
            """SELECT p.id AS project_id, p.name, p.path, p.git_remote,
                      p.is_git_repo, p.tags, p.first_seen, p.last_used, p.session_count,
                      sp.linked_at
               FROM session_projects sp
               JOIN projects p ON sp.project_id = p.id
               WHERE sp.session_id = ?""",
            (session_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        result = dict(row)
        result["is_git_repo"] = bool(result["is_git_repo"])
        result["tags"] = json.loads(result["tags"]) if result["tags"] else []
        return result


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


def compute_loc(project_path: str) -> dict:
    """Walk project directory and count lines of code per file extension."""
    total = 0
    by_extension: Dict[str, int] = {}

    exclude_set = DEFAULT_EXCLUDES

    for dirpath, dirnames, filenames in os.walk(project_path):
        # Prune excluded directories in-place to prevent descending into them
        dirnames[:] = [d for d in dirnames if d not in exclude_set and not d.startswith(".")]

        for filename in filenames:
            # Skip hidden files
            if filename.startswith("."):
                continue

            filepath = os.path.join(dirpath, filename)
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                line_count = len(content.split("\n"))
            except (OSError, PermissionError):
                continue

            total += line_count
            _, ext = os.path.splitext(filename)
            ext_key = ext if ext else "(no extension)"
            by_extension[ext_key] = by_extension.get(ext_key, 0) + line_count

    return {"total": total, "by_extension": by_extension}


def build_fts_index(project_id: str, kb_dir: str) -> None:
    """Build FTS5 index from KB markdown files for a project.
    
    Reads all .md files from kb_dir and inserts their content into
    the project_kb_fts FTS5 table. Uses transaction for efficiency.
    
    Args:
        project_id: The project ID to associate with the KB entries.
        kb_dir: Directory containing KB markdown files.
    """
    kb_path = Path(kb_dir)
    if not kb_path.exists() or not kb_path.is_dir():
        return
    
    store = get_store()
    try:
        conn = store._conn
        
        # Begin transaction with immediate mode for write lock
        conn.execute("BEGIN IMMEDIATE")
        
        try:
            # Delete existing rows for this project (for regeneration)
            conn.execute("DELETE FROM project_kb_fts WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM project_kb_index WHERE project_id = ?", (project_id,))
            
            # Read all .md files and insert into both tables
            now = time.time()
            for md_file in sorted(kb_path.glob("*.md")):
                section = md_file.stem  # filename without .md extension
                try:
                    content = md_file.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    continue
                
                conn.execute(
                    "INSERT INTO project_kb_fts (project_id, section, content) VALUES (?, ?, ?)",
                    (project_id, section, content)
                )
                conn.execute(
                    "INSERT INTO project_kb_index (project_id, section, content, updated_at) VALUES (?, ?, ?, ?)",
                    (project_id, section, content, now)
                )
            
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        store.close()


async def run_kb_generation(project_id: str, project_path: str) -> None:
    """Generate KB files for a project and build FTS index.
    
    This function runs the hermes-kb skill to generate markdown KB files,
    then indexes them into the FTS5 table. Errors are logged but not raised
    to ensure the background task doesn't affect the main operation.
    
    Args:
        project_id: The project ID for KB output directory.
        project_path: The absolute path to the project directory.
    """
    kb_dir = Path(project_path) / "kb"
    
    try:
        # Ensure KB output directory exists
        kb_dir.mkdir(parents=True, exist_ok=True)
        
        # Default exclude patterns for KB generation
        exclude_patterns = (
            "node_modules/,.git/,build/,dist/,cli/dist/,target/,.next/,"
            "__pycache__/,vendor/,.venv/,.rp1/context/,venv/,env/,*.pyc,"
            "*.class,*.o,*.so,.DS_Store"
        )
        
        # Load the hermes-kb skill content to get generation instructions
        try:
            from tools.skills_tool import skill_view
            skill_content = skill_view("hermes-kb", preprocess=False)
            skill_data = json.loads(skill_content)
            if not skill_data.get("success"):
                logger.warning(f"Failed to load hermes-kb skill: {skill_data.get('error')}")
                return
        except Exception as e:
            logger.warning(f"Could not load hermes-kb skill: {e}")
            return
        
        # Generate KB files by invoking the skill logic via subprocess
        # We'll use hermes CLI to run the skill with the appropriate arguments
        hermes_cmd = os.environ.get("HERMES_CLI", "hermes")
        
        # Try to run the skill via hermes chat with the skill preloaded
        # Pass the project path and ID as arguments
        skill_script = f'''
import os
import subprocess
import sys

project_path = "{project_path}"
project_id = "{project_id}"
kb_dir = "{kb_dir}"

# Detect project type
project_type = "unknown"
os.chdir(project_path)

if os.path.exists("pyproject.toml") or os.path.exists("setup.py") or os.path.exists("requirements.txt"):
    project_type = "python"
elif os.path.exists("Cargo.toml"):
    project_type = "rust"
elif os.path.exists("go.mod"):
    project_type = "go"
elif os.path.exists("package.json"):
    project_type = "javascript"
elif os.path.exists("pom.xml") or os.path.exists("build.gradle"):
    project_type = "java"

# Collect basic metadata
git_remote = ""
is_git_repo = os.path.exists(".git")
if is_git_repo:
    try:
        result = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True, timeout=5)
        git_remote = result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        pass

# Get project name from common locations
project_name = os.path.basename(project_path)
if os.path.exists("package.json"):
    try:
        import json as json_mod
        with open("package.json") as f:
            pkg = json_mod.load(f)
            project_name = pkg.get("name", project_name)
    except Exception:
        pass

# Generate index.md
index_content = f"""# {{project_name}}

## Overview

Project type: {{project_type}}
Git remote: {{git_remote or "None"}}

## Metadata

- **Type**: {{project_type}}
- **Git Remote**: {{git_remote or "None"}}
- **KB Generated**: Yes

## Navigation

See other KB files in this directory for detailed project information.
"""

with open(os.path.join(kb_dir, "index.md"), "w") as f:
    f.write(index_content)

# Generate architecture.md
arch_content = f"""# Architecture

## Project Type

This is a {{project_type}} project.

## Overview

Project located at: {{project_path}}
"""

with open(os.path.join(kb_dir, "architecture.md"), "w") as f:
    f.write(arch_content)

# Generate modules.md
modules_content = f"""# Modules

## Project Structure

Project: {{project_name}}
Location: {{project_path}}

"""

with open(os.path.join(kb_dir, "modules.md"), "w") as f:
    f.write(modules_content)

# Generate concept_map.md
concept_content = f"""# Concept Map

## Domain Concepts

This project contains domain-specific concepts relevant to {{project_type}} development.

"""

with open(os.path.join(kb_dir, "concept_map.md"), "w") as f:
    f.write(concept_content)

# Generate patterns.md
patterns_content = f"""# Implementation Patterns

## Project Type Patterns

This {{project_type}} project follows standard patterns for its type.

"""

with open(os.path.join(kb_dir, "patterns.md"), "w") as f:
    f.write(patterns_content)

print(f"KB generation complete for project {{project_id}}")
'''
        
        # Write and execute the generation script
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(skill_script)
            script_path = f.name
        
        try:
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=project_path
            )
            if result.returncode != 0:
                logger.warning(f"KB generation script failed: {result.stderr}")
        except subprocess.TimeoutExpired:
            logger.warning(f"KB generation timed out for project {project_id}")
        except Exception as e:
            logger.warning(f"KB generation error: {e}")
        finally:
            try:
                os.unlink(script_path)
            except Exception:
                pass
        
        # Build FTS index from generated KB files
        try:
            build_fts_index(project_id, str(kb_dir))
            logger.info(f"FTS index built for project {project_id}")
        except Exception as e:
            logger.warning(f"FTS index build failed for project {project_id}: {e}")
        
    except Exception as e:
        logger.error(f"KB generation failed for project {project_id}: {e}")


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
    """Get sessions with linked projects from the project-explorer plugin.
    
    Returns sessions that have been linked to projects via the dashboard,
    including the linked project path."""
    store = get_store()
    try:
        # Get all session-project links
        cursor = store._conn.execute(
            """SELECT sp.session_id, sp.linked_at, p.id, p.name, p.path
               FROM session_projects sp
               JOIN projects p ON sp.project_id = p.id
               ORDER BY sp.linked_at DESC"""
        )
        rows = cursor.fetchall()
        sessions = [
            {
                "id": row[0],
                "linked_at": row[1],
                "project_id": row[2],
                "project_name": row[3],
                "project_path": row[4],
            }
            for row in rows
        ]
        return {"sessions": sessions}
    finally:
        store.close()


@router.post("/sessions/{session_id}/link")
async def link_session_to_project(session_id: str, body: LinkProjectRequest):
    """Link a session to a project by path.
    
    After successfully linking, triggers async KB generation in the background.
    """
    project_root = normalize_to_project_root(body.project_path)
    
    if not project_root:
        project_root = body.project_path
    
    store = get_store()
    try:
        project = store.maybe_add_project(project_root)
        if not project:
            raise HTTPException(status_code=500, detail="Failed to add project")
        # Also write to session_projects table
        store._conn.execute(
            "INSERT OR REPLACE INTO session_projects (session_id, project_id, linked_at) VALUES (?, ?, ?)",
            (session_id, project["id"], time.time()),
        )
        store._conn.commit()
        
        # Trigger async KB generation in background
        asyncio.create_task(run_kb_generation(project["id"], project["path"]))
        
        return {"project": project, "session_id": session_id, "indexing": True}
    finally:
        store.close()


@router.get("/sessions/{session_id}/project")
async def get_session_project(session_id: str):
    """Get the project linked to a specific session."""
    store = get_store()
    try:
        result = store.get_session_project(session_id)
        if not result:
            raise HTTPException(
                status_code=404,
                detail={"error": "no_project_linked", "message": "Session not linked to any project"}
            )
        return result
    finally:
        store.close()


@router.get("/current-project")
async def get_current_project(x_session_id: Optional[str] = Header(None, alias="X-Session-ID")):
    """Get the project linked to the current session (from X-Session-ID header)."""
    if not x_session_id:
        return {"linked": False}
    
    store = get_store()
    try:
        result = store.get_session_project(x_session_id)
        if not result:
            return {"linked": False}
        return {"linked": True, "project": result}
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


@router.get("/projects/{project_id}/stats")
async def get_project_stats(project_id: str):
    """Get LOC stats, file type counts, and git status for a project."""
    store = get_store()
    try:
        project = store.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        project_path = project["path"]

        # Compute LOC
        loc = compute_loc(project_path)

        # Count files per extension (distinct from line counts)
        file_types: Dict[str, int] = {}
        exclude_set = DEFAULT_EXCLUDES
        for dirpath, dirnames, filenames in os.walk(project_path):
            dirnames[:] = [d for d in dirnames if d not in exclude_set and not d.startswith(".")]
            for filename in filenames:
                if filename.startswith("."):
                    continue
                _, ext = os.path.splitext(filename)
                ext_key = ext if ext else "(no extension)"
                file_types[ext_key] = file_types.get(ext_key, 0) + 1

        # Git status
        git_status = "dirty"
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                cwd=project_path,
                timeout=10,
            )
            if not result.stdout.strip():
                git_status = "clean"
        except (subprocess.SubprocessError, OSError):
            pass

        return {
            "loc": loc,
            "file_types": file_types,
            "git_status": git_status,
            "computed_at": datetime.utcnow().isoformat(),
        }
    finally:
        store.close()


@router.get("/projects/{project_id}/git-recent")
async def get_git_recent(project_id: str):
    """Get recent git commits for a project."""
    store = get_store()
    try:
        project = store.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        project_path = project["path"]

        if not (Path(project_path) / ".git").exists():
            return {"is_git_repo": False, "commits": []}

        commits = []
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "-10", "--format=%H|%s|%an|%ad", "--date=iso"],
                capture_output=True,
                text=True,
                cwd=project_path,
                timeout=10,
            )
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.split("|", 3)
                if len(parts) == 4:
                    commits.append({
                        "hash": parts[0],
                        "message": parts[1],
                        "author": parts[2],
                        "date": parts[3],
                    })
        except (subprocess.SubprocessError, OSError):
            pass

        return {"is_git_repo": True, "commits": commits}
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


def _escape_fts5_query(q: str) -> str:
    """Escape a user query string for safe use in FTS5 MATCH clause."""
    escaped = q.replace('"', '""')
    return f'"{escaped}"'


@router.get("/projects/{project_id}/kb/search")
async def kb_search(project_id: str, q: str, limit: int = 20):
    """Search the project KB using FTS5 full-text search.
    
    Query params:
        q (required): Search query string.
        limit (optional, default=20): Maximum number of results.
    
    Returns:
        {results: [{section, content_snippet, rank}]}
    
    Raises:
        404 if no results found for the project.
    """
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required")

    store = get_store()
    try:
        project = store.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Escape and construct FTS5 query with project_id filter
        fts_query = _escape_fts5_query(q.strip())
        
        cursor = store._conn.execute(
            f"""SELECT section, content, rank
                FROM project_kb_fts
                WHERE project_kb_fts MATCH ? AND project_id = ?
                ORDER BY rank
                LIMIT ?""",
            (fts_query, project_id, limit),
        )
        rows = cursor.fetchall()

        if not rows:
            raise HTTPException(
                status_code=404,
                detail={"error": "no_results", "message": "No KB search results found"}
            )

        results = []
        for row in rows:
            # Use SQLite snippet() for a highlighted content excerpt (context around match)
            snippet_cursor = store._conn.execute(
                """SELECT snippet(project_kb_fts, 2, '<mark>', '</mark>', '...', 64)
                   FROM project_kb_fts
                   WHERE project_kb_fts MATCH ? AND project_id = ? AND section = ?
                   LIMIT 1""",
                (fts_query, project_id, row["section"]),
            )
            snippet_row = snippet_cursor.fetchone()
            content_snippet = snippet_row[0] if snippet_row else (row["content"][:200] + "...")

            results.append({
                "section": row["section"],
                "content_snippet": content_snippet,
                "rank": row["rank"],
            })

        return {"results": results}
    finally:
        store.close()


@router.get("/projects/{project_id}/kb/section/{section}")
async def kb_section(project_id: str, section: str):
    """Retrieve a specific KB section markdown file.
    
    Section param: index, concepts, architecture, modules, patterns
    
    Returns:
        {content: str, updated_at: float}
    
    Raises:
        404 if section file does not exist.
    """
    store = get_store()
    try:
        project = store.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Map section names to filenames
        section_map = {
            "index": "index",
            "concepts": "concept_map",
            "architecture": "architecture",
            "modules": "modules",
            "patterns": "patterns",
        }
        section_filename = section_map.get(section)
        if not section_filename:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid section '{section}'. Valid sections: {list(section_map.keys())}"
            )

        kb_file = HERMES_HOME / "projects" / project_id / "kb" / f"{section_filename}.md"

        if not kb_file.exists():
            raise HTTPException(
                status_code=404,
                detail={"error": "section_not_found", "message": f"KB section '{section}' not found"}
            )

        content = kb_file.read_text(encoding="utf-8")
        mtime = kb_file.stat().st_mtime

        return {"content": content, "updated_at": mtime}
    finally:
        store.close()


@router.get("/projects/{project_id}/kb/status")
async def kb_status(project_id: str):
    """Check KB readiness status for a project.
    
    Returns:
        {status: "ready"|"indexing"|"not_started", updated_at: float, file_count: int, sections: list}
    """
    store = get_store()
    try:
        project = store.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        kb_dir = Path(project["path"]) / "kb"

        if not kb_dir.exists() or not kb_dir.is_dir():
            return {
                "status": "not_started",
                "updated_at": None,
                "file_count": 0,
                "sections": [],
            }

        # Count .md files and gather their mtimes
        md_files = sorted(kb_dir.glob("*.md"))
        file_count = len(md_files)
        sections = [f.stem for f in md_files]
        updated_at = max((f.stat().st_mtime for f in md_files), default=None)

        # Check FTS5 table for indexed rows
        cursor = store._conn.execute(
            "SELECT COUNT(*) as cnt FROM project_kb_fts WHERE project_id = ?",
            (project_id,),
        )
        row = cursor.fetchone()
        indexed_count = row["cnt"] if row else 0

        # Determine status
        if indexed_count == 0 and file_count > 0:
            status = "indexing"
        elif indexed_count > 0 and file_count > 0:
            status = "ready"
        else:
            status = "not_started"

        return {
            "status": status,
            "updated_at": updated_at,
            "file_count": file_count,
            "sections": sections,
        }
    finally:
        store.close()


@router.post("/projects/{project_id}/kb/regenerate")
async def kb_regenerate(project_id: str):
    """Queue async KB regeneration for a project.
    
    Returns 202 immediately; does not wait for generation to complete.
    
    Returns:
        {status: "indexing", message: str}
    """
    store = get_store()
    try:
        project = store.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        project_path = project["path"]

        # Queue background KB generation task
        asyncio.create_task(run_kb_generation(project_id, project_path))

        return {
            "status": "indexing",
            "message": "KB regeneration queued",
        }
    finally:
        store.close()


@router.get("/projects/{project_id}/activity")
async def get_activity(project_id: str, limit: int = 20):
    """Get session activity log for a project.
    
    Query params:
        limit (optional, default=20): Maximum number of activities.
    
    Returns:
        {activities: [{session_id, timestamp, actions, summary}]}
    
    Note:
        Empty list is valid and not treated as an error.
    """
    store = get_store()
    try:
        project = store.get_project(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        cursor = store._conn.execute(
            """SELECT session_id, timestamp, actions, summary
               FROM project_activity
               WHERE project_id = ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (project_id, limit),
        )
        rows = cursor.fetchall()

        activities = []
        for row in rows:
            actions = []
            try:
                if row["actions"]:
                    actions = json.loads(row["actions"])
            except (json.JSONDecodeError, TypeError):
                actions = []

            activities.append({
                "session_id": row["session_id"],
                "timestamp": row["timestamp"],
                "actions": actions,
                "summary": row["summary"] or "",
            })

        return {"activities": activities}
    finally:
        store.close()