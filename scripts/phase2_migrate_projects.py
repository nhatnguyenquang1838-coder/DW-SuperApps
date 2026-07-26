from pathlib import Path
import json
import textwrap

root = Path('.')


def rewrite(path: str, replacements: list[tuple[str, str]]) -> None:
    target = root / path
    text = target.read_text(encoding='utf-8')
    for old, new in replacements:
        text = text.replace(old, new)
    target.write_text(text, encoding='utf-8')


rewrite('workspace.yaml', [
    ('path: powers/gwc', 'path: projects/gwc'),
    ('path: powers/ua', 'path: projects/ua'),
    ('path: powers/task-me', 'path: projects/task-me'),
    ('path: systems/rental-home', 'path: projects/rental-home'),
    ('source: Egonex-AI/Understand-Anything', 'source: nhatnguyenquang1838-coder/Understand-Anything'),
])
workspace = root / 'workspace.yaml'
text = workspace.read_text(encoding='utf-8')
project_needle = '    source: nhatnguyenquang1838-coder/Understand-Anything\n    roles:\n'
power_needle = '    source: nhatnguyenquang1838-coder/Understand-Anything\n    enabled: true\n'
if project_needle not in text or power_needle not in text:
    raise SystemExit('UA workspace provenance anchors missing')
text = text.replace(
    project_needle,
    '    source: nhatnguyenquang1838-coder/Understand-Anything\n'
    '    upstream: Egonex-AI/Understand-Anything\n'
    '    roles:\n',
    1,
)
text = text.replace(
    power_needle,
    '    source: nhatnguyenquang1838-coder/Understand-Anything\n'
    '    upstream: Egonex-AI/Understand-Anything\n'
    '    enabled: true\n',
    1,
)
workspace.write_text(text, encoding='utf-8')

for power in ('gwc', 'task-me'):
    rewrite(
        f'manifests/powers/{power}.yaml',
        [(f'path: powers/{power}', f'path: projects/{power}')],
    )
rewrite('manifests/powers/ua.yaml', [
    ('path: powers/ua', 'path: projects/ua'),
    ('source: Egonex-AI/Understand-Anything', 'source: nhatnguyenquang1838-coder/Understand-Anything'),
    ('repository: Egonex-AI/Understand-Anything', 'repository: nhatnguyenquang1838-coder/Understand-Anything'),
    (
        'Upstream submodule remains available as migration fallback.',
        'The controlled fork is the active source submodule; '
        'Egonex-AI/Understand-Anything remains recorded as upstream provenance.',
    ),
])
ua = root / 'manifests/powers/ua.yaml'
text = ua.read_text(encoding='utf-8')
source_anchor = '  source: nhatnguyenquang1838-coder/Understand-Anything\n'
submodule_anchor = (
    '      submodule:\n'
    '        repository: nhatnguyenquang1838-coder/Understand-Anything\n'
)
if source_anchor not in text or submodule_anchor not in text:
    raise SystemExit('UA manifest provenance anchors missing')
text = text.replace(
    source_anchor,
    source_anchor + '  upstream: Egonex-AI/Understand-Anything\n',
    1,
)
text = text.replace(
    submodule_anchor,
    submodule_anchor + '        upstreamRepository: Egonex-AI/Understand-Anything\n',
    1,
)
ua.write_text(text, encoding='utf-8')

schema_path = root / 'schemas/power-manifest.schema.json'
schema = json.loads(schema_path.read_text(encoding='utf-8'))
spec = schema['properties']['spec']['properties']
spec['path']['pattern'] = '^(projects|powers)/[a-z0-9][a-z0-9-]*$'
spec['upstream'] = {'type': 'string', 'pattern': '^[^/\\s]+/[^/\\s]+$'}
submodule = spec['distribution']['properties']['modes']['properties']['submodule']['properties']
submodule['upath']['pattern'] = '^(projects|powers)/[a-z0-9][a-z0-9-]*$'
submodule['upstreamRepository'] = {
    'type': 'string',
    'pattern': '^[^/\\s]+/[^/\\s]+$',
}
schema_path.write_text(json.dumps(schema, indent=2) + '\n', encoding='utf-8')

updates = {
    '.codex/README.md': [('systems/rental-home', 'projects/rental-home')],
    '.codex/skills/gwc/SKILL.md': [('../../../powers/gwc', '../../../projects/gwc')],
    '.codex/skills/task-me/SKILL.md': [('../../../powers/task-me', '../../../projects/task-me')],
    '.codex/skills/ua/SKILL.md': [('../../../powers/ua', '../../../projects/ua')],
    '.kiro/skills/gwc/SKILL.md': [('../../../powers/gwc', '../../../projects/gwc')],
   '.kiro/skills/task-me/SKILL.md': [('../.././powers/task-me', '../../../projects/task-me')],
    '.kiro/skills/ua/SKILL.md': [('../../../powers/ua', '../../../projects/ua')],
    '.kiro/steering/workspace-powers.md': [
        ('systems/rental-home', 'projects/rental-home'),
        ('powers/gwc', 'projects/gwc'),
        ('powers/ua', 'projects/ua'),
        ('powers/task-me', 'projects/task-me'),
    ],
    'hosts/openclaw-acpx/manifest.yaml': [
        ('powers/gwc', 'projects/gwc'),
        ('powers/ua', 'projects/ua'),
        ('powers/task-me', 'projects/task-me'),
    ],
    'README.md': [
        ('systems/rental-home', 'projects/rental-home'),
        (
            'The current checkout keeps compatibility paths under `powers/*` and '
            '`systems/*`. They are registered as projects now and will move physically '
            'into `projects/*` in a later reviewed change.',
            'All editable source repositories live below `projects/*`. Root `powers/` '
            'contains only non-submodule routing assets, while installed packages remain '
            'under `.dw/powers/*`.',
        ),
        ('controlled source project planned', 'controlled source project under `projects/ua`'),
    ],
    'docs/MULTI_HOST_SETUP.md': [('systems/rental-home', 'projects/rental-home')],
    'docs/POWER_CONSUMER_RUNTIME_V1.md': [('systems/rental-home', 'projects/rental-home')],
    'docs/WORKSPACE_OPERATIONS.md': [
        ('systems/rental-home', 'projects/rental-home'),
        ('powers/gwc', 'projects/gwc'),
        ('powers/ua', 'projects/ua'),
        ('powers/task-me', 'projects/task-me'),
    ],
}
for path, replacements in updates.items():
    rewrite(path, replacements)

rewrite('.kilo/plans/1784987769805-ua-full-analysis-plan.md', [
    ('`powers/ua`', '`projects/ua`'),
    ('cd powers/ua/', 'cd projects/ua/'),
    ('systems/rental-home', 'projects/rental-home'),
    (
        '`powers/*` (gwc, ua, task-me, bmad), `projects/rental-home`',
        '`projects/*` (gwc, ua, task-me, rental-home), `powers/bmad`',
    ),
])

graph = root / '.ua/knowledge-graph.json'
text = graph.read_text(encoding='utf-8')
text = text.replace('document:powers/gwc/', 'document:projects/gwc/')
text = text.replace('"filePath": "powers/gwc/', '"filePath": "projects/gwc/')
text = text.replace(
    'powers/gwc provides governance, powers/ua provides semantic analysis, '
    'powers/task-me provides implementation planning, and powers/bmad',
    'projects/gwc provides governance, projects/ua provides semantic analysis, '
    'projects/task-me provides implementation planning, and powers/bmad',
)
graph.write_text(text, encoding='utf-8')

migration = root / 'docs/installation/MIGRATION.md'
text = migration.read_text(encoding='utf-8')
for old, new in (
    ('powers/gwc', 'projects/gwc'),
    ('powers/ua', 'projects/ua'),
    ('powers/task-me', 'projects/task-me'),
    ('systems/rental-home', 'projects/rental-home'),
):
    text = text.replace(old, new)
appendix = '''
## Phase 2 source-project path migration

The canonical source-project paths are now `projects/gwc`, `projects/ua`, `projects/task-me`, and `projects/rental-home`.

For an existing clone, first preserve or commit any dirty child-repository changes. Then synchronize the renamed submodules:

```bash
git submodule deinit -f -- powers/gwc powers/ua powers/task-me systems/rental-home || true
git submodule sync --recursive
git submodule update --init --recursive
./bin/dw project list
./bin/dw validate
```

Do not delete or overwrite dirty legacy submodule worktrees automatically. UA now uses `nhatnguyenquang1838-coder/Understand-Anything` as the active source origin. `Egonex-AI/Understand-Anything` remains the documented upstream provenance. To roll back, reset the Super Project commit and run `git submodule sync --recursive` followed by `git submodule update --init --recursive`.
'''
if '## Phase 2 source-project path migration' not in text:
    text = text.rstrip() + '\n\n' + textwrap.dedent(appendix).strip() + '\n'
migration.write_text(text, encoding='utf-8')

rewrite('tests/test_project_registry.py', [
    ('"path": "powers/gwc"', '"path": "projects/gwc"'),
    (
        '"powers/gwc": "https://github.com/example/gwc.git"',
        '"projects/gwc": "https://github.com/example/gwc.git"',
    ),
])
tests = root / 'tests/test_project_registry.py'
text = tests.read_text(encoding='utf-8')
marker = '    def test_unknown_project_reference_fails_closed(self) -> None:\n'
method = '''    def test_current_workspace_rejects_legacy_source_roots(self) -> None:
        current_root = Path(__file__).resolve().parents[1]
        current = registry.load_yaml(current_root / "workspace.yaml")
        for project in current["projects"]:
            if set(project["roles"]) & {"power-source", "product", "system"}:
                self.assertTrue(project["path"].startswith("projects/"))
        gitmodules = (current_root / ".gitmodules").read_text(encoding="utf-8")
        for legacy in ("powers/gwc", "powers/ua", "powers/task-me", "systems/rental-home"):
            self.assertNotIn(f"path = {legacy}", gitmodules)

'''
if method not in text:
    text = text.replace(marker, method + marker)
tests.write_text(text, encoding='utf-8')

rewrite('tests/test_workspace_distribution_routing.py', [
    ('root / "systems" / "rental-home"', 'root / "projects" / "rental-home"'),
    ('path: systems/rental-home', 'path: projects/rental-home'),
])
