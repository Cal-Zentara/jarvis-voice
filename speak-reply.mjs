#!/usr/bin/env node
// Speaks Claude's last reply out loud using Kokoro, running locally.
// Wired to the Stop hook. No API, no credits.

import fs from 'node:fs';
import { spawn } from 'node:child_process';

import os from 'node:os';
import path from 'node:path';

const VOICE_DIR = path.join(os.homedir(), '.claude', 'voice');
const SERVER_PY = path.join(VOICE_DIR, 'server.py');
// The taskbar icon drops this file when you switch the voice off. Without it,
// this hook would quietly start the server again on the very next reply.
const MUTED = path.join(VOICE_DIR, 'muted');
const PORT = 5210;
const MAX_CHARS = 600;

const quit = () => process.exit(0);

if (fs.existsSync(MUTED)) quit();

// The hook gets a JSON payload on stdin.
let raw = '';
for await (const chunk of process.stdin) raw += chunk;

let payload;
try {
  payload = JSON.parse(raw);
} catch {
  quit();
}

const transcript = payload.transcript_path;
if (!transcript || !fs.existsSync(transcript)) quit();

// Walk the transcript backwards for the most recent assistant text.
const lines = fs.readFileSync(transcript, 'utf8').split('\n').filter(Boolean);
let text = '';
for (let i = lines.length - 1; i >= 0; i--) {
  let entry;
  try {
    entry = JSON.parse(lines[i]);
  } catch {
    continue;
  }
  if (entry.type !== 'assistant') continue;
  const content = entry.message?.content;
  if (!Array.isArray(content)) continue;
  const said = content
    .filter((b) => b.type === 'text')
    .map((b) => b.text)
    .join(' ')
    .trim();
  if (said) {
    text = said;
    break;
  }
}
if (!text) quit();

// Strip the things that sound terrible read aloud.
text = text
  .replace(/```[\s\S]*?```/g, ' ')
  .replace(/`[^`]*`/g, ' ')
  .replace(/!?\[([^\]]*)\]\([^)]*\)/g, '$1')
  .replace(/^\s*[-*+]\s+/gm, '')
  .replace(/[*_#>|]/g, '')
  .replace(/\s+/g, ' ')
  .trim();

if (!text) quit();
if (text.length > MAX_CHARS) {
  const cut = text.slice(0, MAX_CHARS);
  const stop = Math.max(cut.lastIndexOf('. '), cut.lastIndexOf('? '), cut.lastIndexOf('! '));
  text = stop > 100 ? cut.slice(0, stop + 1) : cut;
}

// Hand the text to the voice server, which already has Kokoro in memory.
const send = async () => {
  const res = await fetch(`http://127.0.0.1:${PORT}`, { method: 'POST', body: text });
  return res.ok;
};

try {
  await send();
} catch {
  // Server isn't up yet - start it, wait for it to load, then try once more.
  // Use the exact interpreter the installer used - a different python3 on
  // PATH won't have the packages, and the server would die on import.
  let launcher = process.platform === 'win32' ? 'pythonw' : 'python3';
  try {
    launcher = fs.readFileSync(path.join(VOICE_DIR, 'python-path'), 'utf8').trim() || launcher;
  } catch {
    /* not written yet - fall back to PATH */
  }
  const child = spawn(launcher, [SERVER_PY], { detached: true, stdio: 'ignore' });
  // Without a listener this throws asynchronously and kills the whole hook.
  child.on('error', () => {});
  child.unref();
  for (let i = 0; i < 40; i++) {
    await new Promise((r) => setTimeout(r, 500));
    try {
      await fetch(`http://127.0.0.1:${PORT}`, { method: 'GET' });
      break;
    } catch {
      /* still loading */
    }
  }
  try {
    await send();
  } catch {
    quit();
  }
}

process.exit(0);
