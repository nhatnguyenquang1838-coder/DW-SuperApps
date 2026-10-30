import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const workflow = readFileSync(
  resolve(process.cwd(), '../../.github/workflows/ci-dw-observation.yml'),
  'utf8',
);
const playwrightConfig = readFileSync(resolve(process.cwd(), 'playwright.config.ts'), 'utf8');
const semanticSpec = readFileSync(resolve(process.cwd(), 'e2e/fixture-preview-r1.spec.ts'), 'utf8');
const typecheckBaseline = JSON.parse(readFileSync(resolve(process.cwd(), 'scripts/typecheck-tests-baseline.json'), 'utf8'));

describe('DW Observation CI delivery contract', () => {
  it('preserves the established triggers, read-only permission and required job identity', () => {
    expect(workflow).toContain('branches: [integration/SCRUM-820-dwo-v2, main]');
    expect(workflow).toContain('branches: [main]');
    expect(workflow).toContain('contents: read');
    expect(workflow).toMatch(/jobs:\s*\n\s+typecheck-tests:/);
  });

  it('exports runner scratch paths at step runtime, never from unavailable job-env context', () => {
    const jobEnvelope = workflow.split(/^    steps:\s*$/m)[0];
    expect(jobEnvelope).not.toContain('${{ runner.');
    expect(workflow).toContain('"$RUNNER_TEMP"');
    expect(workflow).toContain('>> "$GITHUB_ENV"');
    expect(workflow).toContain('TMPDIR=%s\\nDWO_R3_SCRATCH_ROOT=%s\\n');
  });

  it('runs full Vitest and both production and test typechecks', () => {
    expect(workflow).toMatch(/pnpm\s+run\s+test(?:\s|$)/);
    expect(workflow).toMatch(/pnpm\s+run\s+typecheck(?:\s|$)/);
    expect(workflow).toContain('pnpm run typecheck:tests');
    expect(workflow).toContain('pnpm run typecheck:tests:strict');
  });

  it('requires zero test-code type debt rather than merely staying below a stale allowance', () => {
    expect(typecheckBaseline.count).toBe(0);
  });

  it('does not count skipped Python integration tests as successful qualification coverage', () => {
    expect(workflow).toContain('--junitxml=ci-pytest.xml');
    expect(workflow).toContain("s.get('skipped','0')");
    expect(workflow).toContain('==0');
    expect(workflow).toContain('StateGraph');
    expect(workflow).toContain('SqliteSaver');
  });

  it('uses the bound fixture spec without retries or snapshot auto-updates', () => {
    expect(workflow).toContain('playwright test e2e/fixture-preview-r1.spec.ts');
    expect(workflow).toContain('--retries=0');
  });

  it('qualifies Python 3.12 against installed app extras with real LangGraph imports and pytest', () => {
    expect(workflow).toContain('python-version: "3.12"');
    expect(workflow).toContain("python -m pip install -e '.[qualification,test]'");
    expect(workflow).toContain('import langgraph');
    expect(workflow).toContain('import langgraph.checkpoint.sqlite');
    expect(workflow).toContain('pytest -q');
    expect(workflow).not.toContain('--ignore');
    expect(workflow).not.toContain('--continue-on-collection-errors');
  });

  it('executes the fixture Chromium semantic cold-start E2E and mock-source production build', () => {
    expect(workflow).toMatch(/playwright install(?:\s+--with-deps)?\s+chromium/);
    expect(workflow).toContain('PLAYWRIGHT_SOURCE: fixture');
    expect(workflow).toContain('fixture-preview-chromium');
    expect(playwrightConfig).toContain("testMatch: '**/fixture-preview-r1.spec.ts'");
    expect(workflow).toMatch(/PLAYWRIGHT_SOURCE:\s*mock/);
    expect(workflow).toMatch(/pnpm\s+run\s+build/);
    expect(workflow).not.toContain('--update-snapshots');
  });

  it('keeps semantic screenshot capture separate from OS baseline certification', () => {
    expect(workflow).toContain('semantic-e2e');
    expect(semanticSpec).toContain('page.screenshot(');
    expect(workflow).toContain('snapshot-baseline');
    expect(workflow).toMatch(/OS snapshot baseline certification/i);
  });

  it('bounds job and long-running steps and always uploads logs and Playwright artifacts', () => {
    expect(workflow).toMatch(/timeout-minutes:\s*(?:[1-9]|[1-5]\d|60)\s*\n/);
    expect(workflow).toContain('if: always()');
    expect(workflow).toContain('actions/upload-artifact@v4');
    expect(workflow).toMatch(/(logs|log).*[\s\S]*(test-results|playwright-report)/i);
    expect(workflow).not.toMatch(/continue-on-error:\s*true/);
  });
});
