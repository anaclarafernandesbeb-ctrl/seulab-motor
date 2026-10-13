"""Transcribe a video locally with Whisper (faster-whisper). No API key, no cost.

SeuLab adaptation of video-use: the original sent audio to ElevenLabs Scribe.
This version runs Whisper on the user's own computer and writes the result in
the same JSON shape Scribe returns (a `words` list with `word` and `spacing`
entries), so pack_transcripts.py, render.py and the rest of the skill work
unchanged.

Extracts mono 16kHz audio via ffmpeg, runs faster-whisper with word-level
timestamps, writes <edit_dir>/transcripts/<video_stem>.json.

Cached: if the output file already exists, transcription is skipped.

Differences from Scribe, on purpose or by necessity:
- No speaker diarization: every word gets speaker_id "speaker_0".
- No audio events ((laughter), (applause)).
- Whisper tends to drop filler words. An initial prompt full of fillers
  nudges it to keep them; silences still show up as gaps between words.

Usage:
    python helpers/transcribe.py <video_path>
    python helpers/transcribe.py <video_path> --edit-dir /custom/edit
    python helpers/transcribe.py <video_path> --language pt
    python helpers/transcribe.py <video_path> --model large-v3

Model: --model, or SEULAB_WHISPER_MODEL, default "large-v3-turbo".
The first run downloads the model (about 1.6 GB for large-v3-turbo).
"""

from __future__ import annotations

import argparse
import array
import json
import math
import os
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path


DEFAULT_MODEL = os.environ.get("SEULAB_WHISPER_MODEL", "large-v3-turbo")

# Whisper writes what it expects to hear. A prompt that already contains
# fillers makes it far more likely to keep the "é", "hum", "tipo" the editor
# needs to see in order to cut them.
FILLER_PROMPTS = {
    "pt": "Éé... hum, então, tipo, né? Ahn, assim, é... eu, eu acho que, hum, sabe?",
    "en": "Umm, uh, so, like, you know? Uh, I mean, um... I, I think that, hmm.",
    "es": "Eh... este, pues, o sea, ¿no? Ehm, bueno, eh... yo, yo creo que, mmm.",
}

_model = None
_model_name = None
_model_lock = threading.Lock()


def load_api_key() -> str:
    """Kept for compatibility with transcribe_batch.py. Local Whisper needs no key."""
    return ""


def get_model(name: str = DEFAULT_MODEL):
    """Load the Whisper model once per process. GPU when there is one, CPU otherwise."""
    global _model, _model_name
    with _model_lock:
        if _model is not None and _model_name == name:
            return _model
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            sys.exit("faster-whisper is not installed. Run: pip install faster-whisper")
        device, compute_type = "cpu", "int8"
        try:
            import ctranslate2
            if ctranslate2.get_cuda_device_count() > 0:
                device, compute_type = "cuda", "float16"
        except Exception:
            pass
        _model = WhisperModel(name, device=device, compute_type=compute_type)
        _model_name = name
        return _model


def count_audio_tracks(video_path: Path) -> int:
    """How many audio streams the container holds."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=index", "-of", "csv=p=0", str(video_path)],
        capture_output=True, text=True,
    )
    return len([ln for ln in out.stdout.splitlines() if ln.strip()])


def peak_dbfs(wav_path: Path) -> float:
    """Peak level of a 16-bit PCM wav, in dBFS. -inf for digital silence."""
    peak = 0
    with wave.open(str(wav_path), "rb") as w:
        while frames := w.readframes(1 << 16):
            samples = array.array("h", frames)
            peak = max(peak, max(samples), -min(samples))
    return 20 * math.log10(peak / 32768) if peak > 0 else float("-inf")


def extract_audio(video_path: Path, dest: Path, audio_track: int = 0) -> None:
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-map", f"0:a:{audio_track}",
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
        str(dest),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def to_scribe_shape(segments, language: str | None, model_name: str) -> dict:
    """Turn faster-whisper segments into the JSON shape Scribe returns.

    Every word becomes {"type": "word"}; every gap between two words becomes
    {"type": "spacing"} with the gap's start/end, which is what
    pack_transcripts.py reads to find silences.
    """
    words: list[dict] = []
    prev_end: float | None = None
    for seg in segments:
        for w in seg.words or []:
            text = (w.word or "").strip()
            if not text:
                continue
            start, end = round(float(w.start), 3), round(float(w.end), 3)
            if end < start:
                end = start
            if prev_end is not None:
                words.append({
                    "text": " ",
                    "start": prev_end,
                    "end": max(prev_end, start),
                    "type": "spacing",
                    "speaker_id": "speaker_0",
                })
            words.append({
                "text": text,
                "start": start,
                "end": end,
                "type": "word",
                "speaker_id": "speaker_0",
                "logprob": round(math.log(max(float(w.probability), 1e-6)), 4),
            })
            prev_end = end
    return {
        "language_code": language,
        "text": " ".join(w["text"] for w in words if w["type"] == "word"),
        "words": words,
        "transcriber": f"faster-whisper/{model_name}",
    }


def run_whisper(audio_path: Path, language: str | None, model_name: str) -> dict:
    model = get_model(model_name)
    prompt = FILLER_PROMPTS.get(language or "pt", FILLER_PROMPTS["pt"])
    # The model is shared between threads in batch mode; one transcription at a time.
    with _model_lock:
        segments, info = model.transcribe(
            str(audio_path),
            language=language,
            word_timestamps=True,
            initial_prompt=prompt,
            condition_on_previous_text=False,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300, "speech_pad_ms": 200},
        )
        segments = list(segments)
    return to_scribe_shape(segments, language or info.language, model_name)


def transcript_path(edit_dir: Path, video: Path, audio_track: int = 0) -> Path:
    """Where a video's transcript lands. Track 0 keeps the plain name."""
    suffix = "" if audio_track == 0 else f".track{audio_track}"
    return edit_dir / "transcripts" / f"{video.stem}{suffix}.json"


def transcribe_one(
    video: Path,
    edit_dir: Path,
    api_key: str = "",
    language: str | None = None,
    num_speakers: int | None = None,
    verbose: bool = True,
    audio_track: int = 0,
    model_name: str = DEFAULT_MODEL,
) -> Path:
    """Transcribe a single video. Returns path to transcript JSON.

    `api_key` and `num_speakers` are accepted for compatibility and ignored:
    local Whisper needs no key and does not separate speakers.
    """
    transcripts_dir = edit_dir / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    out_path = transcript_path(edit_dir, video, audio_track)

    if out_path.exists():
        if verbose:
            print(f"cached: {out_path.name}")
        return out_path

    if verbose:
        print(f"  extracting audio from {video.name}", flush=True)
        if num_speakers and num_speakers > 1:
            print("  note: local Whisper does not separate speakers; all words are speaker_0", flush=True)

    n_tracks = count_audio_tracks(video)
    if n_tracks > 1 and verbose:
        print(f"  note: {video.name} has {n_tracks} audio tracks, using track "
              f"{audio_track + 1} (--audio-track to change)", flush=True)

    t0 = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        audio = Path(tmp) / f"{video.stem}.wav"
        extract_audio(video, audio, audio_track)

        peak = peak_dbfs(audio)
        if peak < -60.0:
            raise RuntimeError(
                f"track {audio_track + 1} of {video.name} is silent "
                f"(peak {peak:.1f} dBFS). "
                + (f"The file has {n_tracks} audio tracks; try --audio-track "
                   + " or ".join(str(i) for i in range(n_tracks) if i != audio_track) + "."
                   if n_tracks > 1 else "Check the source audio.")
            )

        if verbose:
            print(f"  transcribing {video.stem} locally with Whisper {model_name} "
                  "(first run downloads the model)", flush=True)
        payload = run_whisper(audio, language, model_name)

    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    dt = time.time() - t0

    if verbose:
        kb = out_path.stat().st_size / 1024
        n_words = sum(1 for w in payload["words"] if w["type"] == "word")
        print(f"  saved: {out_path.name} ({kb:.1f} KB) in {dt:.1f}s")
        print(f"    words: {n_words}")

    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Transcribe a video locally with Whisper")
    ap.add_argument("video", type=Path, help="Path to video file")
    ap.add_argument("--edit-dir", type=Path, default=None,
                    help="Edit output directory (default: <video_parent>/edit)")
    ap.add_argument("--language", type=str, default=None,
                    help="Optional ISO language code (e.g., 'pt'). Omit to auto-detect.")
    ap.add_argument("--num-speakers", type=int, default=None,
                    help="Accepted for compatibility; local Whisper does not separate speakers.")
    ap.add_argument("--audio-track", type=int, default=0,
                    help="Zero-based audio track to transcribe (OBS: 0 = game, 1 = mic).")
    ap.add_argument("--model", type=str, default=DEFAULT_MODEL,
                    help=f"Whisper model (default: {DEFAULT_MODEL}). "
                         "Smaller and faster: medium, small. Most accurate: large-v3.")
    args = ap.parse_args()

    video = args.video.resolve()
    if not video.exists():
        sys.exit(f"video not found: {video}")

    edit_dir = (args.edit_dir or (video.parent / "edit")).resolve()

    transcribe_one(
        video=video,
        edit_dir=edit_dir,
        language=args.language,
        num_speakers=args.num_speakers,
        audio_track=args.audio_track,
        model_name=args.model,
    )


if __name__ == "__main__":
    main()
