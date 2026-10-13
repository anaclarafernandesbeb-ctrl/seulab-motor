---
name: video-use-install
description: Install the SeuLab copy of video-use into the current agent (Claude Code or Codex) with ffmpeg and local Whisper, so a non-programmer can start editing immediately.
---

# video-use install (SeuLab · local Whisper)

Use this file only for first-time install or reconnect. For daily editing, read `SKILL.md`. Always read `helpers/` — that's where the scripts live.

This is the SeuLab (Pulso Lab) adaptation of [browser-use/video-use](https://github.com/browser-use/video-use). The only functional change: transcription runs **locally with Whisper (faster-whisper)** instead of ElevenLabs Scribe. No API key, no per-use cost.

## Who you are talking to

A person who does not program, speaking Portuguese. Talk in simple Brazilian Portuguese, one step at a time. Before every command that installs something, say in one sentence what it is and why, then ask for permission. If something fails, explain the error in plain words and fix it yourself whenever possible.

## What must exist at the end

1. This repo cloned to a stable path: `~/SeuLab/motor` (on Windows: `%USERPROFILE%\SeuLab\motor`).
2. `ffmpeg` and `ffprobe` on PATH.
3. Python 3.10+ with the deps from `pyproject.toml`, including `faster-whisper`.
4. The skill registered with the current agent, so it can find `SKILL.md`.
5. A folder for the user's videos: `~/SeuLab/meus-videos`.

## Steps

### 1. Clone

```bash
test -d ~/SeuLab/motor || git clone https://github.com/anaclarafernandesbeb-ctrl/seulab-motor ~/SeuLab/motor
cd ~/SeuLab/motor && git pull --ff-only
```

### 2. Python and dependencies

Check `python3 --version` (Windows: `py --version`). If Python is missing or older than 3.10, install it (macOS: `brew install python`; Windows: `winget install Python.Python.3.12`, or python.org with "Add to PATH" checked).

Use a virtual environment inside the repo so nothing else on the computer changes:

```bash
cd ~/SeuLab/motor
python3 -m venv .venv
.venv/bin/pip install -e .          # Windows: .venv\Scripts\pip install -e .
```

From now on, run helpers with the venv's Python (`.venv/bin/python helpers/...`, Windows `.venv\Scripts\python helpers\...`). Write that path into the user's `CLAUDE.md`/`AGENTS.md` note in step 4 so later sessions use it.

### 3. ffmpeg

```bash
# macOS
command -v ffmpeg >/dev/null || brew install ffmpeg
# Windows
# winget install Gyan.FFmpeg      (then close and reopen the app so PATH updates)
# Debian / Ubuntu
# sudo apt-get update && sudo apt-get install -y ffmpeg
```

If Homebrew is missing on macOS, install it from brew.sh first (it asks for the computer password in the terminal; tell the user that typing the password shows nothing on screen, and that this is normal). Never invent or ask to see a password.

### 4. Register the skill

A symlink of the whole directory, so `helpers/` sits next to `SKILL.md`:

- Claude Code: `mkdir -p ~/.claude/skills && ln -sfn ~/SeuLab/motor ~/.claude/skills/video-use`
- Codex: `mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills" && ln -sfn ~/SeuLab/motor "${CODEX_HOME:-$HOME/.codex}/skills/video-use"`
- Windows without symlink permission: copy the folder instead, or create a junction with `mklink /J`.

Also create `~/SeuLab/meus-videos/CLAUDE.md` and `~/SeuLab/meus-videos/AGENTS.md` with one short note: this folder is for SeuLab edits, read the `video-use` skill, use local Whisper with `--language pt`, use the Python at `~/SeuLab/motor/.venv`, talk to me in simple Portuguese.

### 5. Download the Whisper model (one time)

The default model is `large-v3-turbo` (about 1.6 GB, good Portuguese, reasonable speed on a normal computer). Tell the user it is a one-time download that can take several minutes. Pre-download it:

```bash
~/SeuLab/motor/.venv/bin/python -c "from faster_whisper import WhisperModel; WhisperModel('large-v3-turbo', device='cpu', compute_type='int8'); print('modelo pronto')"
```

If the computer has little memory (8 GB or less) or the download keeps failing, use `medium` instead and save `SEULAB_WHISPER_MODEL=medium` in the notes from step 4.

### 6. Verify end to end

Prove it with a real file, not just file checks:

```bash
cd ~/SeuLab/meus-videos
ffmpeg -y -f lavfi -i testsrc=size=1080x1920:rate=30 -f lavfi -i sine=frequency=440 -t 3 -shortest -c:v libx264 -pix_fmt yuv420p -c:a aac teste-seulab.mp4
~/SeuLab/motor/.venv/bin/python ~/SeuLab/motor/helpers/transcribe.py teste-seulab.mp4 --language pt
~/SeuLab/motor/.venv/bin/python ~/SeuLab/motor/helpers/timeline_view.py --help >/dev/null && echo "helpers OK"
```

The test clip is a tone, so 0 words is the expected result; what matters is that the command finishes and writes `edit/transcripts/teste-seulab.json`. Then delete `teste-seulab.mp4` and the `edit/` folder it created.

### 7. Hand off

Tell the user, in Portuguese, in one short message:

- "Pronto! O SeuLab está instalado."
- Their videos go in the folder `SeuLab/meus-videos` (show the full path).
- To edit, open that folder in the app and paste the edit request from the student area.
- The finished video appears in `meus-videos/edit/final.mp4`.

## Keeping it current

`cd ~/SeuLab/motor && git pull --ff-only`, then `.venv/bin/pip install -e .` if `pyproject.toml` changed.

## Cold-start reminders

- Symlink or copy the **whole directory**, not just `SKILL.md`.
- HyperFrames, Remotion and Manim are optional animation engines, installed the first time a project needs one. HyperFrames needs Node.js 22+.
- The first transcription of a long video on CPU is slow (roughly the video's own length, or more, on older laptops). Warn the user and suggest short clips for the first test.
