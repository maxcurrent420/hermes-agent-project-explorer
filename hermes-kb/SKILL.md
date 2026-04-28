---
name: hermes-kb
description: "Generates project knowledge base using map-reduce architecture — spawns parallel agents for concept, architecture, module, and pattern analysis, then merges outputs"
tools: Bash, Read, Glob, Grep, delegate_task
model: inherit
arguments:
  - name: PROJECT_PATH
    type: string
    required: false
    description: "Absolute path to the project directory. Auto-detected from plugin API if omitted."
  - name: PROJECT_ID
    type: string
    required: false
    description: "Unique identifier for the project. Auto-detected from plugin API if omitted."
  - name: EXCLUDE_PATTERNS
    type: string
    required: false
    default: "node_modules/,.git/,build/,dist/,cli/dist/,target/,.next/,__pycache__/,vendor/,.venv,venv/,env/"
    description: "Directories and patterns to exclude from scanning"
---

# Hermes KB - Map-Reduce Knowledge Base Generator

## Auto-Detection

## Session ID

Hermes automatically substitutes this tag $/{HERMES_SESSION_ID/} with the session ID, so you will see the actual session data instead of a "hermes_session_id" tag here: `${HERMES_SESSION_ID}` at runtime. 
That means your current session ID is `${HERMES_SESSION_ID}`
Use it directly in curl commands:

```bash
curl -s -H "X-Session-ID: ${HERMES_SESSION_ID}" \
  "http://localhost:9119/api/plugins/project-explorer/current-project"
```


If `linked: true` in response, extract:
- `project.path` → use as PROJECT_PATH
- `project.id` → use as PROJECT_ID

If API returns `linked: false` or is unreachable, prompt for path. If PROJECT_PATH was explicitly provided, skip the API call.

## Execution Architecture

```
Phase 1 (Sequential):  Scan and categorize files → categorized file lists
Phase 2 (Parallel):    4 Analysis Agents (2 batches) → KB sections (concept_map, arch, modules, patterns)
Phase 3 (Sequential):  Merge outputs → Write KB files
```

**CRITICAL**: This is an ORCHESTRATOR. You must delegate to sub-agents, not do all the work yourself.

## Parameters

| Parameter | Required | Description |
|-----------|----------|-------------|
| PROJECT_PATH | Yes | Absolute path to project directory |
| PROJECT_ID | Yes | Project identifier for output directory |
| EXCLUDE_PATTERNS | No | Patterns to exclude |

## Phase 1: Scan and Categorize Files

1. **Setup output directory**:

   ```bash
KB_DIR="$PROJECT_PATH/kb"
mkdir -p "$KB_DIR"
   ```

2. **Scan project structure**:

   ```bash
   cd "$PROJECT_PATH"
   
   # Get all relevant files
   find . -type f \
     \( -name "*.py" -o -name "*.js" -o -name "*.ts" -o -name "*.tsx" \
        -o -name "*.rs" -o -name "*.go" -o -name "*.java" -o -name "*.cs" \
        -o -name "*.md" -o -name "*.yaml" -o -name "*.yml" -o -name "*.toml" \) \
     ! -path "*/node_modules/*" ! -path "*/.git/*" ! -path "*/dist/*" \
     ! -path "*/build/*" ! -path "*/__pycache__/*" ! -path "*/target/*" \
     2>/dev/null | head -200
   ```

3. **Categorize files into KB sections**:

   | Category | Files to include |
   |----------|--------------|
   | index_files | README.md, package.json, pyproject.toml, main.*, index.*, app.* |
   | concept_files | README.md, docs/, *types*, *schema*, *model*, domain/ |
   | arch_files | config*, Dockerfile, docker-compose*, .github/, entry points |
   | module_files | src/, lib/, package/, module/, */__init__.py |

   Build arrays:
   - INDEX_FILES: files for project overview
   - CONCEPT_FILES: files for domain concepts
   - ARCH_FILES: files for architecture
   - MODULE_FILES: files for module breakdown

## Phase 2: Delegate to Parallel Agents (CRITICAL)

**IMPORTANT - Concurrency limit**: The delegate_task default max is 3 concurrent children. If you need 4+ agents, use two separate delegate_task calls.

**Spawn all agents in parallel using TWO delegate_task calls (due to 3 concurrent limit):**

**First batch (2 agents):**
```python
delegate_task(
  tasks=[
    {
      "goal": "Extract domain concepts from project files for concept_map.md. Analyze the code to identify: core entities, domain terminology, relationships between concepts, business rules, data models. Return markdown content ready and save it as proj/kb/concept_map.md where proj is the linked project directory.",
      "context": "PROJECT_PATH: {PROJECT_PATH}\nFILES: {concept_files_list}\nPROJECT_ID: {PROJECT_ID}",
      "toolsets": ["terminal", "file"]
    },
    {
      "goal": "Map system architecture from project files for architecture.md. Analyze to identify: architectural patterns (MVC, microservice, layered, etc.), system layers, component interactions, data flows, external integrations. Return markdown with a Mermaid diagram and save it as proj/kb/architecture.md where proj is the linked project directory.",
      "context": "PROJECT_PATH: {PROJECT_PATH}\nFILES: {arch_files_list}\nPROJECT_ID: {PROJECT_ID}",
      "toolsets": ["terminal", "file"]
    }
  ]
)
```

**Second batch (2 agents):**
```python
delegate_task(
  tasks=[
    {
      "goal": "Analyze modules from project files for modules.md. Identify modules, components, internal dependencies, external dependencies, module metrics (file count, LOC per module). Return markdown content and save it as proj/kb/modules.md where proj is the linked project directory.",
      "context": "PROJECT_PATH: {PROJECT_PATH}\nFILES: {module_files_list}\nPROJECT_ID: {PROJECT_ID}",
      "toolsets": ["terminal", "file"]
    },
    {
      "goal": "Extract implementation patterns from project files for patterns.md. Identify naming conventions, type patterns, error handling strategies, validation approaches, code style patterns. Return markdown content and save it as proj/kb/patterns.md where proj is the linked project directory.",
      "context": "PROJECT_PATH: {PROJECT_PATH}\nFILES: {module_files_list}\nPROJECT_ID: {PROJECT_ID}",
      "toolsets": ["terminal", "file"]
    }
  ]
)
```

**IMPORTANT**:
- Use TWO delegate_task calls for 4 agents (due to 3 concurrent limit)
- Each sub-agent generates markdown content directly (not JSON) and saves to file.
- Pass specific files to analyze in context
- **DO NOT assume sub-agents can write files to PROJECT_PATH** — they may lack file write access to the target directory. Collect their output from task summaries if they fail.

## Phase 3: Merge and Write

After parallel agents complete, merge and write files:

1. **Orchestrator-owned: Generate index.md directly**:

   Create index.md with project overview:
   
   ```markdown
   # {Project Name}

   {One-line description}

   ## Overview

   {2-3 sentence description}

   ## Quick Start

   \`\`\`bash
   {install commands}
   \`\`\`

   ## Entry Points

   | File | Purpose |
   |------|---------|
   | {entry_file} | {description} |

   ## Key Metadata

   - **Type**: {python|javascript|rust|go}
   - **Files Analyzed**: {count}
   - **Last Generated**: {timestamp}

   ## Navigation

   - [Architecture](architecture.md)
   - [Modules](modules.md)
   - [Concept Map](concept_map.md)
   - [Patterns](patterns.md)
   ```

2. **Collect outputs from agents**:

   Sub-agents return content in task summaries. If any file is missing (not written to disk by sub-agent), write_file it from the summary text.

3. **Write all files to the project directory** (or KB_DIR if you created one):

   ```bash
   # Verify files exist
   ls -la "$PROJECT_PATH"/*.md
   ```

   If modules.md or patterns.md are missing, they will be in the modules-patterns agent's summary — extract the markdown and write_file them manually.

## Anti-Loop Directives

**EXECUTE IMMEDIATELY**:
- Do NOT do the analysis yourself - delegate to sub-agents
- Spawn all 4 agents in parallel (TWO delegate_task calls with tasks array, 2 agents each)
- Wait for all agents to complete before Phase 3

**Output Discipline**:
- Return only completion summary with file list
- Do NOT output verbose phase-by-phase progress

**Common Failures**:
- Too many agents (>3): use two separate delegate_task calls
- Sub-agents can't write to project dir: extract markdown from task summaries and write_file manually
- Sub-agent fails completely: generate placeholder content for that section
- If 2+ agents fail: report error with specific failures
