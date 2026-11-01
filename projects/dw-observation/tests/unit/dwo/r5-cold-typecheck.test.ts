import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const projectRoot = path.resolve(__dirname, '../../..');
const pinnedTsc = path.join(projectRoot, 'node_modules', 'typescript', 'bin', 'tsc');
const sourceConfigPath = path.join(projectRoot, 'tsconfig.json');
const componentImports = [
  ['components/dwo/ArtifactViewer.tsx', './ArtifactViewer.module.css'],
  ['components/dwo/NextFlowPanel.tsx', './NextFlowPanel.module.css'],
  ['components/dwo/RunStatusAxes.tsx', './RunStatusAxes.module.css'],
  ['components/dwo/WorkspaceHeader.tsx', './WorkspaceHeader.module.css'],
  ['components/ReplayPane.tsx', './ReplayPane.module.css'],
] as const;
const componentRoots = componentImports.map(([file]) => file);

describe('R5 cold-checkout framework type initialization', () => {
  it('typechecks the real CSS-module imports without generated Next ambient files', () => {
    const sourceConfig = JSON.parse(readFileSync(sourceConfigPath, 'utf8')) as {
      compilerOptions?: { types?: string[] };
    };
    const configuredTypes = sourceConfig.compilerOptions?.types;
    const scratchBase = process.env.DWO_R3_SCRATCH_ROOT ?? os.tmpdir();
    const scratch = mkdtempSync(path.join(scratchBase, 'dwo-r5-cold-tsc-'));

    try {
      const coldConfigPath = path.join(scratch, 'tsconfig.cold.json');
      const coldConfig = {
        extends: sourceConfigPath,
        compilerOptions: {
          incremental: false,
          // Resolve the source config's official type packages from this checkout.
          typeRoots: [
            path.join(projectRoot, 'node_modules', '@types'),
            path.join(projectRoot, 'node_modules'),
          ],
          // Before the fix, constrain discovery to Node to keep the RED focused;
          // after the fix, consume the source config's types verbatim.
          types: configuredTypes ?? ['node'],
        },
        files: componentRoots.map((file) => path.join(projectRoot, file)),
        include: [],
        exclude: [],
      };
      writeFileSync(coldConfigPath, `${JSON.stringify(coldConfig, null, 2)}\n`);

      let compilerOutput = '';
      let compilerExitCode = 0;
      try {
        compilerOutput = execFileSync(
          process.execPath,
          [pinnedTsc, '--noEmit', '--pretty', 'false', '-p', coldConfigPath],
          { cwd: projectRoot, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] },
        );
      } catch (error) {
        const result = error as { status?: number; stdout?: string | Buffer; stderr?: string | Buffer };
        compilerExitCode = result.status ?? 1;
        compilerOutput = `${result.stdout?.toString() ?? ''}${result.stderr?.toString() ?? ''}`;
      }

      expect(componentRoots).toHaveLength(5);
      for (const [component, cssImport] of componentImports) {
        expect(readFileSync(path.join(projectRoot, component), 'utf8')).toContain(cssImport);
      }
      expect(coldConfig.files).not.toContain(path.join(projectRoot, 'next-env.d.ts'));
      expect(coldConfig.files.every((file) => !file.includes(`${path.sep}.next${path.sep}`))).toBe(true);
      expect(compilerExitCode, compilerOutput).toBe(0);
      expect(configuredTypes).toContain('node');
      expect(configuredTypes).toContain('next');
    } finally {
      rmSync(scratch, { recursive: true, force: true });
    }
  });
});
