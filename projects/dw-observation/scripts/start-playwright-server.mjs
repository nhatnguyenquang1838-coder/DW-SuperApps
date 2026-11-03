import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import path from 'node:path';

const source = process.argv[2] ?? 'fixture';
const port = Number(process.argv[3] ?? process.env.PLAYWRIGHT_FIXTURE_PORT ?? 3100);
if (!['fixture', 'mock'].includes(source)) throw new Error(`unsupported fixture source: ${source}`);
if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error(`invalid server port: ${port}`);

const require = createRequire(import.meta.url);
const nextBin = require.resolve('next/dist/bin/next');
const child = spawn(process.execPath, [nextBin, 'dev', '-p', String(port)], {
  cwd: process.cwd(),
  env: { ...process.env, OBSERVATORY_DATA_SOURCE: source },
  stdio: 'inherit',
  shell: false,
});

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => child.kill(signal));
}
child.on('error', (error) => {
  console.error(`Failed to start Next.js via ${nextBin}:`, error);
  process.exitCode = 1;
});
child.on('exit', (code, signal) => {
  process.exitCode = code ?? (signal ? 1 : 0);
});
