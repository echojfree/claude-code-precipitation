# Claude Code Precipitation Plugin

Hermes-Agent-style **automatic knowledge precipitation** for Claude Code. This plugin learns from every session you have with Claude Code, automatically extracting reusable knowledge, preferences, patterns, and references — then persists them as structured memory files that make every future session smarter.

## What It Does

```
Every Claude Code Session
        │
        ▼
┌──────────────────────────┐
│  SessionEnd Hook Fires   │
│  (agent analyzes session)│
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│  Extract Durable Knowledge│
│  • User preferences      │
│  • Feedback & corrections│
│  • Project context       │
│  • External references   │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│  Write to .claude/memory/ │
│  • Deduplicate first     │
│  • Confidence-gate       │
│  • Update MEMORY.md index│
└──────────────────────────┘
           │
           ▼  (periodically)
┌──────────────────────────┐
│  Curator Consolidation   │
│  • Merge similar memories│
│  • Archive stale ones    │
│  • Generate skill drafts │
└──────────────────────────┘
```

### Key Features

- **Automatic**: Runs after every session. No manual work needed.
- **Structured**: Uses Claude Code's native memory system (`.claude/memory/` with MEMORY.md index)
- **Confidence-gated**: High-confidence extractions saved directly; low-confidence ones flagged for review
- **Self-maintaining**: Curator periodically consolidates duplicates, archives stale entries
- **Non-destructive**: Never deletes — only archives. You can always recover.

## Installation

### From Marketplace (Recommended)

First, add the marketplace:

```
/claude marketplace add precipitation-marketplace --source github --repo echojfree/claude-code-precipitation
```

Then install the plugin:

```
/claude plugin install precipitation@precipitation-marketplace
```

### Manual Installation

```bash
git clone https://github.com/echojfree/claude-code-precipitation.git
/claude plugin install ./claude-code-precipitation
```

## Configuration

The plugin works out of the box with sensible defaults. All settings are in `.claude/precip_state.json` within your project.

### Default Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `curator.interval_days` | 7 | Days between curator consolidation runs |
| `curator.paused` | false | Pause automatic curation |
| `lifecycle.stale_after_days` | 30 | Days of inactivity before marking stale |
| `lifecycle.archive_after_days` | 90 | Days of inactivity before archiving |

### Changing Settings

Use the `/curator` command:

```
/curator pause          # Pause automatic curation
/curator resume         # Resume automatic curation
```

Or manually edit `.claude/precip_state.json`.

You can also configure the precipitation model and interval by editing the hooks in your project or user settings.

## Usage

### Automatic (Default)

The plugin works automatically:
- **After each session**: SessionEnd hook analyzes the conversation and extracts up to 3 key learnings
- **Every ~7 days**: Curator consolidates memories and manages the lifecycle

### Manual Commands

```
/precipitate status     # View precipitation statistics
/precipitate now        # Trigger immediate precipitation
/precipitate review     # Review pending low-confidence extractions

/curator status         # View curator state and schedule
/curator run            # Trigger curator consolidation now
/curator pause          # Pause automatic curation
/curator resume         # Resume automatic curation
/curator stats          # Detailed knowledge base statistics
/curator consolidate    # Manually consolidate overlapping memories
```

## How It Works

### Two-Phase Precipitation

**Phase 1 — Quick (SessionEnd)**
- Runs immediately after every session
- Uses Claude Haiku for speed and cost efficiency
- Extracts 1-3 key learnings per session
- Writes directly to `.claude/memory/`

**Phase 2 — Deep (Curator)**
- Runs periodically (default: every 7 days)
- Uses Claude Sonnet for thorough analysis
- Consolidates similar memories
- Archives stale entries
- Generates skill candidates from repeated patterns

### Memory Types

The plugin respects Claude Code's 4 memory types:

| Type | What It Captures |
|------|-----------------|
| `user` | User role, preferences, knowledge level, working style |
| `feedback` | Corrections, confirmed approaches, validated patterns |
| `project` | Deadlines, constraints, architectural decisions, ongoing work |
| `reference` | External dashboards, wikis, issue trackers, Slack channels |

### What Gets Saved (And What Doesn't)

**Saved:**
- User preferences (e.g., "prefers Chinese commit messages")
- Non-obvious project context (e.g., "auth rewrite is for compliance, not tech debt")
- Validated approaches confirmed by the user
- Corrections with reasons why

**Not Saved:** (per Claude Code's memory rules)
- Code patterns derivable from the code itself
- Git history (use `git log` instead)
- One-time debugging fixes
- Content already in CLAUDE.md
- Ephemeral conversation state

### Skill Lifecycle

```
draft → active → stale → archived
  ↑       ↑         │
  └───────┴─────────┘
  (usage reactivates an item)
```

Items transition based on their `last_used_at` timestamp (tracked by the PostToolUse hook).

## Requirements

- Claude Code with plugin support
- Python 3.8+ (for usage tracking script)
- Write access to `.claude/` directory in your project

## Privacy

All analysis happens locally. The precipitation agent runs as a Claude Code agent hook with access to your session transcript. No data is sent to external services beyond what Claude Code normally sends to the API for model inference.

The usage tracking state (`.claude/precip_state.json`) contains only timestamps and counts — no conversation content is stored there.

## Repository Structure

```
claude-code-precipitation-plugin/
├── .claude-plugin/
│   └── plugin.json         # Plugin manifest
├── commands/                # Slash commands
│   ├── precipitate.md      # /precipitate command
│   └── curator.md          # /curator command
├── hooks/
│   └── hooks.json          # SessionEnd + PostToolUse hooks
├── scripts/
│   └── track_usage.py      # Usage tracking script
├── marketplace.json         # Marketplace configuration
└── README.md               # This file
```

## Troubleshooting

### Memories aren't being created
1. Check the plugin is enabled: `/plugin list`
2. Verify hooks are registered: check your settings.json for `hooks` section
3. Check Python is available: `python3 --version`
4. Look for errors in the usage tracker state: `cat .claude/precip_state.json`

### Too many low-quality memories
- Use `/precipitate review` to clean up pending extractions
- Memories with confidence <0.7 are flagged for review — approve only the good ones
- The precipitation agent learns from rejections over time

### Curator not running
- Check it's not paused: `/curator status`
- Manually trigger: `/curator run`
- The default interval is 7 days — it won't run more frequently than that

## License

MIT — see LICENSE file.
