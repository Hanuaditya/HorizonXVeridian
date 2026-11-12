import { spawn } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, '..');

const env = {
  ...process.env,
  DEMO_MODE: 'true',
  NEXT_PUBLIC_DEMO_MODE: 'true',
  APP_ENV: process.env.APP_ENV || 'development',
  SHARED_HMAC_SECRET:
    process.env.SHARED_HMAC_SECRET || 'horizon_veridian_demo_hmac_secret_min_32_bytes_2026',
  PYTHONUNBUFFERED: '1',
};

console.log('\n===============================================================');
console.log('  Horizon Veridian x Gnani AI — Unified Demo Launcher (DEMO_MODE)');
console.log('===============================================================');
console.log('  WorkOS Hub       : http://localhost:3000/workos');
console.log('  Meetings Hub     : http://localhost:3000/meetings');
console.log('  Admin & Maps     : http://localhost:3000/admin');
console.log('  Media Health     : http://localhost:5001/health');
console.log('  WorkOS Health    : http://localhost:8000/health');
console.log('  WorkOS API Docs  : http://localhost:8000/api/docs');
console.log('===============================================================\n');

const isWin = process.platform === 'win32';
const npmCmd = isWin ? 'npm.cmd' : 'npm';

const processes = [
  {
    name: 'media',
    cmd: 'python',
    args: ['app.py'],
    cwd: path.join(rootDir, 'services', 'media'),
  },
  {
    name: 'workos',
    cmd: 'python',
    args: ['-m', 'uvicorn', 'api.main:app', '--host', '0.0.0.0', '--port', '8000'],
    cwd: path.join(rootDir, 'services', 'workos'),
  },
  {
    name: 'web',
    cmd: npmCmd,
    args: ['run', 'dev'],
    cwd: path.join(rootDir, 'apps', 'web'),
  },
];

const children = [];

function shutdown(signal) {
  console.log(`\nStopping all services (${signal})...`);
  for (const child of children) {
    if (!child.killed) {
      child.kill('SIGTERM');
    }
  }
  process.exit(0);
}

process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));

for (const proc of processes) {
  const child = spawn(proc.cmd, proc.args, {
    cwd: proc.cwd,
    env,
    stdio: 'pipe',
    shell: isWin && proc.cmd.endsWith('.cmd'),
  });

  const prefix = `[${proc.name.toUpperCase()}]`;
  child.stdout?.on('data', (chunk) => {
    for (const line of chunk.toString().split(/\r?\n/)) {
      if (line) console.log(`${prefix} ${line}`);
    }
  });
  child.stderr?.on('data', (chunk) => {
    for (const line of chunk.toString().split(/\r?\n/)) {
      if (line) console.error(`${prefix} ${line}`);
    }
  });
  child.on('exit', (code) => {
    console.log(`${prefix} exited with code ${code}`);
  });
  children.push(child);
}

