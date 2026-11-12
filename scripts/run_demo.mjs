import { spawn } from 'child_process';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, '..');
const isLive = process.argv.includes('--live');

function loadRootEnvFile(envPath) {
  const parsed = {};
  if (!fs.existsSync(envPath)) return parsed;
  const raw = fs.readFileSync(envPath, 'utf-8');
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eqIdx = trimmed.indexOf('=');
    if (eqIdx === -1) continue;
    const key = trimmed.slice(0, eqIdx).trim();
    let val = trimmed.slice(eqIdx + 1).trim();
    if (
      (val.startsWith('"') && val.endsWith('"')) ||
      (val.startsWith("'") && val.endsWith("'"))
    ) {
      val = val.slice(1, -1);
    }
    parsed[key] = val;
  }
  return parsed;
}

const fileEnv = isLive ? loadRootEnvFile(path.join(rootDir, '.env')) : {};

const env = {
  ...fileEnv,
  ...process.env,
  DEMO_MODE: isLive ? 'false' : 'true',
  NEXT_PUBLIC_DEMO_MODE: isLive ? 'false' : 'true',
  APP_ENV: process.env.APP_ENV || fileEnv.APP_ENV || 'development',
  SHARED_HMAC_SECRET:
    process.env.SHARED_HMAC_SECRET ||
    fileEnv.SHARED_HMAC_SECRET ||
    'horizon_veridian_demo_hmac_secret_min_32_bytes_2026',
  PYTHONUNBUFFERED: '1',
};

console.log('\n===============================================================');
console.log(
  isLive
    ? '  Horizon Veridian x Gnani AI — Unified LIVE Launcher (DEMO_MODE=false)'
    : '  Horizon Veridian x Gnani AI — Unified Demo Launcher (DEMO_MODE=true)'
);
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

async function checkUrl(url) {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 1500);
    const res = await fetch(url, { signal: controller.signal });
    clearTimeout(timer);
    return res.ok;
  } catch {
    return false;
  }
}

(async function waitForAllReady() {
  const targets = [
    'http://localhost:5001/health',
    'http://localhost:8000/health',
    'http://localhost:3000',
  ];
  for (let i = 0; i < 60; i++) {
    await new Promise((r) => setTimeout(r, 1500));
    const results = await Promise.all(targets.map(checkUrl));
    if (results.every(Boolean)) {
      console.log('\n===============================================================');
      console.log(`  ALL 3 SERVICES READY (${isLive ? 'LIVE MODE' : 'DEMO MODE'})`);
      console.log('  Open WorkOS Hub   -> http://localhost:3000/workos');
      console.log('  Open Meetings Hub -> http://localhost:3000/meetings');
      console.log('===============================================================\n');
      return;
    }
  }
})();
