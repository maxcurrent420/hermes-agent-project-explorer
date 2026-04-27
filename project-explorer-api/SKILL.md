---
name: project-explorer-api
description: "Query and manage project links via the Project Explorer dashboard plugin API. Use this when you need to discover, link, or query project context for the current session."
trigger: "When needing to query the Project Explorer plugin API, discover linked projects, or link a session to a project directory"
---

# Project Explorer Plugin API

The Project Explorer plugin exposes a REST API for discovering and linking projects to Hermes sessions.

**Base URL:** `http://localhost:9119/api/plugins/project-explorer`

**Important:** The plugin runs on port **9119**.

## Key Endpoints

### Link a Session to a Project
```bash
# Link current session to a project path
SESSION_ID="your-session-id"
curl -X POST "http://localhost:9119/api/plugins/project-explorer/sessions/${SESSION_ID}/link" \
  -H "Content-Type: application/json" \
  -d '{"project_path": "/path/to/project"}'
```
Returns: `{project: {...}, session_id: "...", indexing: true}`

### Get Project Linked to a Session
```bash
SESSION_ID="your-session-id"
curl -s "http://localhost:9119/api/plugins/project-explorer/sessions/${SESSION_ID}/project"
```
Returns: `{project_id, name, path, git_remote, is_git_repo, tags, linked_at, ...}`

### Get Current Project (from X-Session-ID header)
```bash
curl -s -H "X-Session-ID: ${HERMES_SESSION_ID}" \
  "http://localhost:9119/api/plugins/project-explorer/current-project"
```

### List All Sessions with Linked Projects
```bash
curl -s "http://localhost:9119/api/plugins/project-explorer/sessions"
```

### Discover Project from Current Terminal CWD
```bash
curl -s "http://localhost:9119/api/plugins/project-explorer/discover"
```

### List All Tracked Projects
```bash
curl -s "http://localhost:9119/api/plugins/project-explorer/projects"
```

### Get Project Stats (LOC, file types, git status)
```bash
curl -s "http://localhost:9119/api/plugins/project-explorer/projects/{project_id}/stats"
```

### Get Project File Tree
```bash
curl -s "http://localhost:9119/api/plugins/project-explorer/projects/{project_id}/tree?depth=3"
```

### Search Project KB
```bash
curl -s "http://localhost:9119/api/plugins/project-explorer/projects/{project_id}/kb/search?q=authentication"
```

## Getting Session ID

The session ID is available as `${HERMES_SESSION_ID}` environment variable, or from:
- Session JSON files in `~/.hermes/sessions/`
- The `session_id` field in Hermes state

## Notes

- Linking a project triggers async KB generation in the background
- Projects are auto-discovered from git roots or common project markers (.git, package.json, Cargo.toml, pyproject.toml, etc.)
- The plugin uses SQLite at `~/.hermes/projects.db` for storage
