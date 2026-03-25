# Phase 4: Manual Testing & Marketplace Submission Guide

**Prerequisite:** All plugin files are committed on `gsp-86-rollforward-impl`. These steps are done by you (Matt), not agents.

---

## Part 1: Test Plugin Installation

### 1.1 Claude Code Plugin

**Test: Self-hosted marketplace install**

In a Claude Code session (any project, not gaspatchio-core):

```
/plugin marketplace add opioinc/gaspatchio-core
```

Then:

```
/plugin install gaspatchio@opioinc/gaspatchio-core
```

**Verify:**
- Run `/plugin` — gaspatchio should appear in the list
- Type a message like "I want to build a term life model" — the agent should pick up `gaspatchio-model-building` or `gaspatchio-model-discovery` skill
- Check that AGENTS.md content is loaded (ask "what are the gaspatchio performance rules?" — it should know without invoking a skill)

**If it doesn't work:**
- Check `/plugin` output for error messages
- The repo must be public (or you must have access) for marketplace add to work
- Try the local path fallback: clone the repo somewhere else, then `/plugin install /path/to/gaspatchio-core`

---

### 1.2 VS Code / Copilot Plugin

**Prerequisite:** VS Code with GitHub Copilot extension. Enable preview feature:

Settings → search `chat.plugins.enabled` → set to `true`

**Test: Marketplace install**

Add to your VS Code user settings (`settings.json`):

```json
{
  "chat.plugins.marketplaces": ["opioinc/gaspatchio-core"]
}
```

Then in Copilot Chat, search for `@agentPlugins gaspatchio`.

**Alternative: Direct install from source**

Command Palette → `Chat: Install Plugin From Source` → paste the repo URL:
```
https://github.com/opioinc/gaspatchio-core.git
```

**Verify:**
- Skills should appear — try invoking one in Copilot Chat
- Ask a gaspatchio question to see if AGENTS.md context is loaded

**Gotchas (from research):**
- VS Code caches marketplace data aggressively — if nothing appears, reload the window (`Cmd+Shift+P` → `Developer: Reload Window`)
- Manifest errors are silent — if the plugin doesn't show up, validate `.github/plugin.json` manually
- If switching between `org/repo` and full HTTPS URL format, you may need to reload to bust cache

---

### 1.3 Cursor Plugin

**Test: Auto-detection**

Open the gaspatchio-core repo in Cursor. The `.cursor-plugin/` directory should be auto-detected.

**Verify:**
- Check Cursor's AI settings/rules panel — gaspatchio skills should appear
- Ask Cursor to "build a gaspatchio model" — it should pick up the building skill

**If it doesn't work:**
- Cursor may need a restart after first detecting the plugin directory
- Check Cursor's docs for the latest plugin format — the `.cursor-plugin/` convention may have evolved

---

### 1.4 `npx skills add` (Universal)

**Test: Install skills into a fresh project**

Create a temporary test directory and install:

```bash
mkdir /tmp/test-gaspatchio-skills && cd /tmp/test-gaspatchio-skills
npx skills add gaspatchio/gaspatchio-core
```

**Verify:**
- Check that skill files were copied: `ls .skills/` or `.agents/skills/` (depends on the skills CLI's target directory)
- Each of the 6 skills should have its SKILL.md and references
- Open the directory in Claude Code or VS Code and verify skills are discovered

**If it doesn't work:**
- The `npx skills add` command expects the repo to be public
- Check the Vercel skills CLI docs for the expected source layout
- Fallback: users can always clone the repo directly

**Cleanup:**
```bash
rm -rf /tmp/test-gaspatchio-skills
```

---

## Part 2: Marketplace Submissions

### 2.1 Anthropic: `claude-plugins-official`

**What:** PR to add gaspatchio to Anthropic's curated plugin directory.

**Repo:** https://github.com/anthropics/claude-plugins-official

**Steps:**

1. Fork `anthropics/claude-plugins-official`
2. Check the existing format — look at how other plugins are listed (likely a JSON or YAML catalog file, or a directory entry)
3. Add a gaspatchio entry with:
   - Name: `gaspatchio`
   - Description: "Actuarial modeling toolkit — skills for building, reconciling, and reviewing gaspatchio models"
   - Source: `opioinc/gaspatchio-core` (or the correct org)
   - Version: `1.0.0`
4. Open a PR with:
   - Title: `Add gaspatchio actuarial modeling plugin`
   - Description explaining what it is, who it's for, and the 6 skills it provides
5. Wait for Anthropic review

**After acceptance**, users install with:
```
/plugin install gaspatchio@claude-plugins-official
```

---

### 2.2 GitHub: `awesome-copilot`

**What:** PR to add gaspatchio to the default VS Code / Copilot plugin marketplace.

**Repo:** https://github.com/github/awesome-copilot

**Steps:**

1. Fork `github/awesome-copilot`
2. Check the submission format (likely a catalog JSON or markdown list)
3. Add gaspatchio with:
   - Name: `gaspatchio`
   - Description: "Actuarial modeling toolkit for building, reconciling, and reviewing actuarial projection models"
   - Category: Developer Tools / Domain-Specific
   - Source: `opioinc/gaspatchio-core`
   - Skills count: 6
4. Open a PR
5. Wait for GitHub review

---

### 2.3 Vercel Skills Directory (Optional)

**What:** Register gaspatchio on https://skills.sh for discoverability via `npx skills search`.

**Steps:**

1. Check https://skills.sh for submission instructions
2. The Vercel skills CLI likely auto-indexes repos that follow the `skills/*/SKILL.md` convention
3. If manual submission is needed, follow their process
4. After listing, users can find gaspatchio via: `npx skills search gaspatchio`

---

## Part 3: Post-Submission Checklist

After testing and submissions are done:

```
- [ ] Claude Code: plugin installs and skills are discovered
- [ ] Claude Code: AGENTS.md content is loaded automatically
- [ ] VS Code: plugin installs via marketplace settings or direct source
- [ ] VS Code: skills appear in Copilot Chat
- [ ] Cursor: auto-detects .cursor-plugin/ when repo opened
- [ ] npx skills add: installs all 6 skills into a fresh project
- [ ] PR submitted to anthropics/claude-plugins-official
- [ ] PR submitted to github/awesome-copilot
- [ ] (Optional) Listed on skills.sh
```

---

## Troubleshooting Reference

| Symptom | Likely Cause | Fix |
|---|---|---|
| Plugin doesn't appear after install | Aggressive caching | Reload editor window |
| Skills not discovered | Manifest path error | Validate JSON, check relative paths resolve |
| AGENTS.md not loaded | Editor doesn't auto-detect | Add `@AGENTS.md` reference to CLAUDE.md or `.cursorrules` |
| `npx skills add` fails | Repo not public | Make repo public, or use direct clone |
| VS Code shows no `@agentPlugins` | Feature not enabled | Set `chat.plugins.enabled: true` in settings |
| Silent failure, no error | Wrong JSON key in manifest | Check `mcpServers` not `servers`; check `skills` paths |
| Marketplace PR rejected | Missing metadata | Check catalog format in target repo, match existing entries |
