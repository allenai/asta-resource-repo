# Asta Skills

This directory contains Claude Code skills for the Asta document management system.

## Available Skills

### asta-documents.md

Complete document management skill for tracking research papers, documentation, and resources.

**Features:**
- Add, search, update, and remove documents
- Tag-based organization
- Multiple search modes (keyword, semantic, hybrid)
- Content fetching with automatic caching
- JSON output for scripting

## Installation

### Prerequisites

1. **Install the CLI tool:**
   ```bash
   uv tool install git+https://github.com/allenai/asta-resource-repo.git
   ```

2. **Install Claude Code** if you haven't already

### Install the Skill

**Option 1: Direct download**
```bash
curl -o ~/.claude/skills/asta-documents.md https://raw.githubusercontent.com/allenai/asta-resource-repo/main/skills/asta-documents.md
```

**Option 2: Copy from repository**
```bash
# If you have the repo cloned
cp skills/asta-documents.md ~/.claude/skills/
```

**Option 3: Manual installation**
1. Open this repository in GitHub
2. Navigate to `skills/asta-documents.md`
3. Copy the raw content
4. Create `~/.claude/skills/asta-documents.md` and paste

### Verify Installation

1. Restart Claude Code (or reload skills)
2. Type `/asta-documents` to see if the skill is available
3. You should also see aliases: `/asta`, `/asta-docs`, `/docs`

## Usage

Once installed, use the skill in Claude Code:

```
💬 "Use /asta-documents to add a paper at https://arxiv.org/pdf/1706.03762.pdf
    about Transformers, tags: ai, research"

💬 "Use /asta-documents to search for papers about attention mechanisms"

💬 "Use /asta-documents to list all documents tagged with research"
```

## Updating

To update the skill to the latest version:

```bash
curl -o ~/.claude/skills/asta-documents.md https://raw.githubusercontent.com/allenai/asta-resource-repo/main/skills/asta-documents.md
```

Then restart Claude Code or reload skills.

## Documentation

- **Skill documentation**: See `asta-documents.md` for complete command reference
- **Project README**: [../README.md](../README.md)
- **Developer guide**: [../CLAUDE.md](../CLAUDE.md)

## Troubleshooting

**Skill not found:**
- Check file is in `~/.claude/skills/asta-documents.md`
- Restart Claude Code
- Verify frontmatter has correct YAML format

**Commands fail:**
- Verify CLI is installed: `asta-documents --help`
- Check you're in a directory (creates `.asta/documents/index.yaml`)
- See troubleshooting in `asta-documents.md`

## Contributing

To contribute or modify skills:

1. Edit the skill file in this directory
2. Test with Claude Code
3. Submit a pull request
4. External users can update via curl once merged

## License

MIT License - Same as the parent project
