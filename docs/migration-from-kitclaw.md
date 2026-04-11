# Migrating from KitClaw to Z-Core

**Note:** The original KitClaw V1 repository has been officially archived. Z-Core is the direct V2 successor that unifies the runtime, skills, and memory into a single zero-dependency CLI.

## What Changed

1. **No More Bash Installers:** You no longer need to clone `KitClaw` and run `bash install.sh`. 
2. **Unified CLI:** Everything is now under the `zcore` command namespace (e.g., `zcore memory search`, `zcore skill install`, `zcore session start`).
3. **Ghost Agent:** Z-Core introduces an autonomous LLM backend that works between sessions to compact context and extract memories efficiently.
4. **Python Native:** Z-Core is a real Python package (`pip install zcore`).

## Migration Steps

### 1. Install Z-Core

```bash
git clone https://github.com/cloud99277/Z-Core
cd Z-Core
pip install -e .
zcore init
```

### 2. Auto-configure Agents

Z-Core can automatically set up Claude Code, Gemini CLI, and Codex CLI to use its memory and skill hooks:

```bash
zcore setup all
```

*(This will safely inject the necessary instructions and create backups of your original configs).*

### 3. Migrate Local State & Custom Skills

Z-Core is 100% backward compatible with KitClaw's directories (`~/.ai-memory`, `~/.ai-skills`). 

- Your existing `~/.ai-memory/whiteboard.json` and topics will be read automatically.
- Your installed custom skills in `~/.ai-skills/` will still work.

To install or refresh the bundled core skills:
```bash
zcore skill install --core
```

### 4. Enable RAG (Optional)

If you used the KitClaw RAG engine (`lancedb`), install Z-Core with the optional `[rag]` dependency:

```bash
pip install -e ".[rag]"
zcore knowledge index
```

### 5. Transition CLI Usage

| KitClaw V1 Command | Z-Core V2 Equivalent |
|--------------------|----------------------|
| `python3 memory-search.py ...` | `zcore memory search --query ...` |
| `bash knowledge-search.sh ...` | `zcore knowledge search --query ...` |
| `python3 log-execution.py ...` | Automatically handled by the SkillRouter |
| N/A (Manual hook editing) | `zcore setup all` |

## FAQs

**Q: Do I need to delete my existing `~/.ai-memory/`?**
No. Z-Core uses the exact same memory layout. Your topics, decisions, and history are safe.

**Q: Will my custom skills from `ai-skills-hub` break?**
No. Z-Core is fully backward compatible with the `SKILL.md` frontmatter spec.

**Q: Can I completely delete the `KitClaw` folder now?**
Yes. If you've installed `zcore` and run `zcore skill install --core`, you can delete your old local clone of the KitClaw repository.
