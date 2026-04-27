# Project Explorer Plugin

A Hermes Agent dashboard plugin for tracking projects and linking coding sessions to repositories.

<img width="1884" height="941" alt="image" src="https://github.com/user-attachments/assets/06863d04-7c08-484e-b4bc-647dd9642379" />



## Features

- **Project Tracking**: Automatically discover and track projects from coding sessions
- **File Browser**: Browse file structures from your sessions
- **Session Linking**: Link your coding sessions to their respective repositories
- **Session-Project Mapping**: Associate sessions with their root projects
- **Project Statistics**: LOC counts, file type distribution, git status
- **Knowledge Base (KB)**: Auto-generated project KB with full-text search
- **Activity Feed**: Session activity log per project
- **Dashboard Tab**: Dedicated "Projects" tab in the Hermes Agent dashboard

## Installation

1. Copy the `project-explorer` folder to your Hermes Agent plugins directory:
   ```bash
   cp -r project-explorer ~/.hermes/hermes-agent/plugins/
   ```

2. Restart Hermes Agent to load the plugin

## API Endpoints

All endpoints are mounted at `/api/plugins/project-explorer/`.

Base URL: `http://localhost:9119/api/plugins/project-explorer` (adjust port as needed)

**Note**: The plugin runs on port **9119**.

---

## Hermes Agent Integration (Optional)

This plugin includes two optional skills for Hermes Agent:

### project-explorer-api Skill
For easy access to the Project Explorer API from other skills or agents, load the skill from this plugin:

```
/project-explorer-api
```

This skill provides curl commands and patterns for:
- Linking sessions to projects
- Querying linked project context
- Auto-discovering projects from terminal CWD
- Searching project knowledge base

See [skill documentation](project-explorer-api/SKILL.md) for details.

### hermes-kb Skill
For generating project knowledge base files, load the skill:

```
/hermes-kb
```

This skill uses map-reduce architecture to spawn parallel agents for concept, architecture, module, and pattern analysis.

See [skill documentation](hermes-kb/SKILL.md) for details.

---

### Session-Project Mapping

Link sessions to projects and retrieve the current project context.

#### GET /sessions/{session_id}/project

Get the project linked to a specific session.

```
GET /api/plugins/project-explorer/sessions/abc123/project
```

Response `200`:
```json
{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "my-app",
  "path": "/home/user/projects/my-app",
  "git_remote": "https://github.com/user/my-app",
  "linked_at": 1714099200.123
}
```

Response `404` (not linked):
```json
{
  "error": "no_project_linked",
  "message": "Session not linked to any project"
}
```

---

#### GET /current-project

Get the project for the current session using the `X-Session-ID` header.

```
GET /api/plugins/project-explorer/current-project
Headers:
  X-Session-ID: abc123
```

Response `200`: Same as `/sessions/{session_id}/project`

Response `422` (missing header):
```json
{
  "error": "missing_session_id",
  "message": "X-Session-ID header is required"
}
```

---

#### POST /sessions/{session_id}/link

Link a session to a project by path. Triggers async KB generation in the background.

```
POST /api/plugins/project-explorer/sessions/abc123/link
Content-Type: application/json

{
  "project_path": "/home/user/projects/my-app/src/main.py"
}
```

The API automatically walks up to find the project root (via `.git`, `package.json`, `Cargo.toml`, etc.).

Response `200`:
```json
{
  "project": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "my-app",
    "path": "/home/user/projects/my-app",
    ...
  },
  "session_id": "abc123",
  "indexing": true
}
```

---

### Project Discovery (Backward Compatible)

#### GET /discover

Discover the current project from the session's terminal working directory. Uses `TERMINAL_CWD` env var, falling back to `cwd`.

```
GET /api/plugins/project-explorer/discover
```

Response `200` (found):
```json
{
  "discovered": true,
  "project": { "id": "...", "name": "...", "path": "..." },
  "cwd": "/home/user/projects/my-app/src"
}
```

Response `200` (not found):
```json
{
  "discovered": false,
  "cwd": "/some/unknown/path"
}
```

---

### Project Management

#### GET /projects

List all tracked projects (ordered by `last_used`).

```
GET /api/plugins/project-explorer/projects
```

Response `200`:
```json
{
  "projects": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "my-app",
      "path": "/home/user/projects/my-app",
      "first_seen": 1714000000.0,
      "last_used": 1714099200.0,
      "session_count": 5,
      "is_git_repo": true,
      "git_remote": "https://github.com/user/my-app",
      "tags": ["python", "web"]
    }
  ]
}
```

#### GET /projects/{project_id}

Get a single project by ID.

#### POST /projects

Manually add a project by path.

```json
{
  "path": "/home/user/projects/my-app"
}
```

#### DELETE /projects/{project_id}

Remove a project from tracking.

#### PUT /projects/{project_id}/tags

Update project tags.

```json
{ "tags": ["python", "api"] }
```

#### GET /projects/{project_id}/tree

Get the file tree for a project (max depth configurable via `?depth=N`).

```
GET /api/plugins/project-explorer/projects/550e8400.../tree?depth=3
```

#### POST /projects/{project_id}/refresh

Re-scan project (update git remote, `last_used`, etc.).

---

### Project Statistics

#### GET /projects/{project_id}/stats

Get LOC statistics, file type distribution, and git status for a project.

```
GET /api/plugins/project-explorer/projects/550e8400.../stats
```

Response `200`:
```json
{
  "loc": {
    "total": 4821,
    "by_extension": {
      ".py": 3200,
      ".md": 450,
      ".json": 171,
      "(no extension)": 1000
    }
  },
  "file_types": {
    ".py": 42,
    ".md": 12,
    ".json": 8
  },
  "git_status": "dirty",
  "computed_at": "2026-04-27T04:15:00.000000"
}
```

`git_status` is `"clean"` if `git status --porcelain` is empty, `"dirty"` otherwise. Returns `"dirty"` if git fails or the path is not a git repo.

---

#### GET /projects/{project_id}/git-recent

Get recent git commits (last 10).

```
GET /api/plugins/project-explorer/projects/550e8400.../git-recent
```

Response `200`:
```json
{
  "is_git_repo": true,
  "commits": [
    {
      "hash": "a1b2c3d4e5f6...",
      "message": "Add user authentication",
      "author": "Jane Developer",
      "date": "2026-04-26 14:32:01 +0000"
    },
    ...
  ]
}
```

Response `200` (not a git repo):
```json
{
  "is_git_repo": false,
  "commits": []
}
```

---

### Knowledge Base (KB) Search

The KB is optional and requires the included hermes-kb skill. When a session is linked to a project, KB generation runs asynchronously in the background. If not yet generated, KB endpoints return `not_started` or 404.

KB sections: `index`, `concepts`, `architecture`, `modules`, `patterns`

#### GET /projects/{project_id}/kb/status

Check KB indexing status for a project.

```
GET /api/plugins/project-explorer/projects/550e8400.../kb/status
```

Response `200` (ready):
```json
{
  "status": "ready",
  "updated_at": 1714099200.0,
  "file_count": 5,
  "sections": ["index", "architecture", "modules", "concept_map", "patterns"]
}
```

Possible `status` values:
- `not_started` — KB directory does not exist or is empty
- `indexing` — markdown files exist but FTS5 index has not been built yet
- `ready` — both files and FTS5 index are present

#### GET /projects/{project_id}/kb/search

Full-text search across the project KB using SQLite FTS5.

```
GET /api/plugins/project-explorer/projects/550e8400.../kb/search?q=authentication&limit=10
```

Query params:
- `q` (required): Search query string.
- `limit` (optional, default=20): Maximum number of results.

Response `200`:
```json
{
  "results": [
    {
      "section": "architecture",
      "content_snippet": "The system uses JWT <mark>authentication</mark> with refresh tokens...",
      "rank": 0.75
    }
  ]
}
```

Response `404` (no results):
```json
{
  "error": "no_results",
  "message": "No KB search results found"
}
```

#### GET /projects/{project_id}/kb/section/{section}

Retrieve a specific KB section as markdown.

```
GET /api/plugins/project-explorer/projects/550e8400.../kb/section/index
GET /api/plugins/project-explorer/projects/550e8400.../kb/section/architecture
GET /api/plugins/project-explorer/projects/550e8400.../kb/section/modules
GET /api/plugins/project-explorer/projects/550e8400.../kb/section/concepts
GET /api/plugins/project-explorer/projects/550e8400.../kb/section/patterns
```

Response `200`:
```json
{
  "content": "# My App\n\n## Overview\n\nProject type: python\n...",
  "updated_at": 1714099200.0
}
```

Response `404` (section not found):
```json
{
  "error": "section_not_found",
  "message": "KB section 'concepts' not found"
}
```

#### POST /projects/{project_id}/kb/regenerate

Queue async KB regeneration for a project. Returns `202 Accepted` immediately — does not wait for generation.

```
POST /api/plugins/project-explorer/projects/550e8400.../kb/regenerate
```

Response `202`:
```json
{
  "status": "indexing",
  "message": "KB regeneration queued"
}
```

---

### Activity Feed

#### GET /projects/{project_id}/activity

Get session activity log for a project.

```
GET /api/plugins/project-explorer/projects/550e8400.../activity?limit=20
```

Query params:
- `limit` (optional, default=20): Maximum number of activities.

Response `200`:
```json
{
  "activities": [
    {
      "session_id": "abc123",
      "timestamp": 1714099200.0,
      "actions": ["file_edit", "code_completion"],
      "summary": "Refactored auth module"
    }
  ]
}
```

Empty list (`[]`) is a valid response and is not treated as an error.

---

## Database

The plugin uses a local SQLite database at `~/.hermes/projects.db` with the following tables:

| Table | Purpose |
|---|---|
| `projects` | Project metadata (path, name, git info, tags) |
| `session_projects` | Session-to-project linkage |
| `project_kb_fts` | FTS5 virtual table for KB full-text search |
| `project_activity` | Session activity log entries |

---

## Usage

- Navigate to the **Projects** tab in the dashboard
- Projects are automatically discovered from your coding sessions
- Click on a project to browse its file structure
- Sessions are linked to their repositories automatically
- Use the KB search to quickly find information about a project
- Check project stats to see LOC, file types, and git status at a glance

## Requirements

- Hermes Agent (latest)
- Python 3.11+

## License

MIT License - see LICENSE file for details.
