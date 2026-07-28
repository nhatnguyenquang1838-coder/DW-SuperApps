# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup: camera names and locations, SSH hosts and aliases, preferred TTS voices, speaker/room names, device nicknames, anything environment-specific.

## DW SuperApps skill routing

The canonical installed skill store is:

`/Users/mac/prj/DW-SuperApps/.dw/powers/`

Use the relevant installed package entrypoint:

- `gwc` → `.dw/powers/gwc/skills/gwc-g0/SKILL.md` or
  `.dw/powers/gwc/skills/gwc-g1/SKILL.md`
- `ua` → `.dw/powers/ua/understand-anything-plugin/skills/understand/SKILL.md`
- `task-me` → `.dw/powers/task-me/.kiro/skills/implementation-task-architect/SKILL.md`
- `bmad` → `.dw/powers/bmad/distribution/skills/bmad/SKILL.md`

Routing rules:

- Read the selected `SKILL.md` before taking that skill's action.
- Use `workspace.yaml`, the relevant `AGENTS.md`, and the installed
  `MANIFEST.json` to validate routing.
- Keep host adapters thin and keep system runtime data in the owning system.
- Do not treat `projects/` source checkouts as the default when an installed
  package exists in `.dw/powers/`.
- Do not expose, copy, or invent secrets, credentials, package identities, or
  validation evidence.

## Local notes

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.

## Related

- [Agent workspace](/concepts/agent-workspace)
