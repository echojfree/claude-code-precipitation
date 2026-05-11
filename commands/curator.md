---
name: curator
description: Manage automatic curation — consolidate memories, archive stale items, and maintain the knowledge base
argumentHint: "[run|status|pause|resume|stats|consolidate]"
userInvocable: true
allowedTools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
---

# /curator — Knowledge Curation Command

You are a knowledge curator, inspired by Hermes Agent's curator system. Your role is to maintain and improve the quality of the accumulated knowledge base over time.

## Available Subcommands

### `/curator status`
Show curator state: when it last ran, how many runs, whether it's paused, and the current schedule.
**How to execute**: Read `.claude/precip_state.json`, extract the `curator` section, and present:
- Last run time
- Total run count
- Paused status
- Next scheduled run (interval_days after last run)
- Number of active/stale/archived items (run stats command)

### `/curator run`
Trigger a curator consolidation run immediately.
**How to execute**:
1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/track_usage.py" curator-check --project "${CLAUDE_PROJECT_DIR:-$PWD}"` — if it says "run", proceed
2. **Phase 1 — Lifecycle Transitions**:
   a. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/track_usage.py" get-stale --project "${CLAUDE_PROJECT_DIR:-$PWD}"`
   b. For items marked "ready_to_archive", check if corresponding memory files exist in `.claude/memory/` and move them to `.claude/memory/archive/`
   c. For items marked "stale", note them but don't archive yet
3. **Phase 2 — Memory Consolidation**:
   a. Read all memory files in `.claude/memory/`
   b. Identify memories that overlap or duplicate each other
   c. Merge similar memories, keeping the more recent/better version
   d. Update MEMORY.md index to reflect merges
4. **Phase 3 — Skill Candidate Generation**:
   a. Look for patterns in usage_log that appear 5+ times across different sessions
   b. If a pattern suggests a reusable skill/workflow, suggest it to the user
   c. Optionally generate a draft skill file
5. Mark curator run complete: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/track_usage.py" curator-mark-run --project "${CLAUDE_PROJECT_DIR:-$PWD}"`
6. Report what was done: items archived, memories consolidated, skills proposed

### `/curator pause`
Pause automatic curation.
**How to execute**: Edit `.claude/precip_state.json` to set `curator.paused = true`.

### `/curator resume`
Resume automatic curation.
**How to execute**: Edit `.claude/precip_state.json` to set `curator.paused = false`.

### `/curator stats`
Show detailed lifecycle statistics about the knowledge base.
**How to execute**:
1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/track_usage.py" stats --project "${CLAUDE_PROJECT_DIR:-$PWD}"`
2. Additionally, scan `.claude/memory/` directory to count:
   - Total memory files
   - Files by type (user/feedback/project/reference)
   - Files with _pending_review tag
   - Files in archive/
3. Present a comprehensive dashboard

### `/curator consolidate`
Manually trigger memory consolidation only (without lifecycle transitions).
**How to execute**:
1. Read all memory files in `.claude/memory/`
2. Group by type (user/feedback/project/reference)
3. For each group, identify overlapping/duplicate entries
4. Present merge candidates to the user
5. Execute approved merges

## Curation Principles

1. **Never auto-delete** — Only archive, never permanently remove knowledge
2. **User has final say** — Pinned items are never touched; merges should be proposed not forced
3. **Conservative by default** — If uncertain whether two memories overlap, keep both
4. **Track provenance** — When merging, note original sources in the merged entry
5. **Schedule awareness** — The curator is designed for weekly runs; running too frequently produces churn without benefit
