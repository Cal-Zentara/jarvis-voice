# Jarvis voice for Claude Code

Say "hey Jarvis", talk, and stop. It types what you said, sends it, and Claude
answers you out loud. You never touch the keyboard. Say "hey Jarvis" again while
it's talking to cut it off.

Works on Windows and Mac.

## Before you start

- **Python** — get it from python.org if you don't have it
- **Wispr Flow**, running.
  On Windows leave its shortcut on the default, Ctrl+Win.
  On Mac change it to **Ctrl+Option+Space** in Flow's settings. Flow defaults to
  the Fn key, and macOS does not let any software press Fn.
- **Claude Code**, desktop app or terminal

On Mac the first run asks for Microphone and Accessibility permission. Say yes
to both, or it can't hear you and can't press keys for you.

## Install

Open a terminal in this folder and run:

```
python install.py
```

About 10 minutes, mostly downloading the voice model. It asks which microphone
you talk into and which voice Claude should answer in.

## Turn it on

Windows:

```
python %USERPROFILE%\.claude\voice\start.py
```

Mac:

```
python3 ~/.claude/voice/start.py
```

Then just talk. To turn it off, add `--stop` to that line.

## The voice Claude answers in

Free by default — Kokoro, running on your own machine. No account, no cost, no
matter how much you talk to it.

For something more human, the installer can take an ElevenLabs API key
(elevenlabs.io, then Developers, then API Keys). It's saved to
`~/.claude/voice/elevenlabs.key` and never leaves your machine. Delete that file
to go back to the free voice.

Whichever you pick is the only one it ever uses. If ElevenLabs fails it stays
quiet and logs why, rather than switching voices on you halfway through.

To change voices, just ask Claude — "make your voice an American woman" — and it
will find the voice, edit `server.py` and restart. `speed` in the same file
controls how fast it talks.

## The pieces

| File | What it does |
|---|---|
| `wake.py` | Listens for "hey Jarvis", hands over to Wispr Flow, presses Enter when you stop talking |
| `server.py` | Speaks Claude's replies, kept warm in memory so it answers instantly |
| `speak-reply.mjs` | The hook that catches each reply and sends it to the server |
| `start.py` | Turns the whole thing on and off |
| `speak.py` | One-shot speak with no server. Kept as a fallback. |

## If something's off

- **It doesn't hear you** — run the installer again and pick a different mic, or
  set `MIC` in `wake.py` to part of your headset's name.
- **It wakes when you didn't say anything** — raise `THRESHOLD` in `wake.py`
  toward 0.8.
- **It cuts you off mid sentence** — raise `SILENCE_MS`.
- **It sends before you're done** — raise `PASTE_WAIT_S`.
- **Your words land in the wrong window** — it types wherever you last clicked,
  so click the Claude box before you talk.
- **You want a different voice** — change `ELEVEN_VOICE` (or `KOKORO_VOICE`) in
  `server.py`. `speed` in the same file controls how fast it talks.
