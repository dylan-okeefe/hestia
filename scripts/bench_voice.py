#!/usr/bin/env python3
"""Voice pipeline benchmark (STT accuracy/speed + TTS speed/intelligibility).

Modes:
    prompts   Print the numbered recording script for voice samples.
    stt       Transcribe a directory of NN.wav samples, report latency/RTF/WER
              against the embedded reference transcripts.
    tts       Synthesize a fixed sentence set, report synthesis latency/RTF,
              write WAVs for listening, and optionally compute round-trip WER
              (transcribe the synthesized audio with a reference STT model —
              an objective intelligibility proxy).

Examples:
    python scripts/bench_voice.py prompts
    python scripts/bench_voice.py stt --samples-dir runtime-data/bench/voice-samples \
        --label whisper-medium-cpu-int8
    python scripts/bench_voice.py tts --label piper-amy-medium --roundtrip-stt medium

Results append to runtime-data/bench/voice-bench.csv.
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import statistics
import struct
import sys
import time
import urllib.request
import wave
from pathlib import Path

# ---------------------------------------------------------------------------
# Fixed prompt/sentence sets — do not edit: changing them invalidates
# comparisons with previously recorded benchmark runs.
# ---------------------------------------------------------------------------

# Recording script for STT samples. Realistic Hestia utterances: short
# commands, questions, names, numbers, dates, and one long ramble.
STT_PROMPTS = [
    "Hey Hestia, what's on my calendar for tomorrow?",
    "Remind me to call the dentist at two thirty PM on Thursday.",
    "Can you add oat milk and eggs to the grocery list?",
    "What's the weather going to be like this weekend?",
    "Set a timer for twenty five minutes.",
    "Did Silas reply to my message about the motherboard?",
    "Search my notes for the Eagle B550 wifi driver issue.",
    "Play something quiet, I'm going to bed.",
    "What's five hundred and twelve divided by thirty two?",
    "Okay so I was thinking, if the second GPU doesn't fit in the case, "
    "we could either return it, or maybe move the whole build into the "
    "Corsair case, but then I'd have to reroute all the front panel cables.",
    "Thanks, that's all for now.",
    "Hmm, actually, never mind, cancel that last reminder.",
]

# TTS sentence set: varied length, punctuation, numbers, a question.
TTS_SENTENCES = [
    "Good morning. You have three meetings today.",
    "Your reminder to call the dentist is set for Thursday at two thirty PM.",
    "I've added oat milk and eggs to the grocery list.",
    "It looks like rain this weekend, with highs around sixty four degrees.",
    "Silas replied to your message about the motherboard an hour ago.",
    "I found two notes mentioning the Eagle B550 wifi driver issue.",
    "Timer set for twenty five minutes. I'll let you know when it's done.",
    "That's a long story, but the short version is that the build went fine, "
    "the second card fit without any trouble, and the only real problem was "
    "a loose front panel connector that took me twenty minutes to find.",
]

PIPER_VOICE_URL = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/"
    "{lang}/{lang}_{region}/{name}/{quality}/{voice}.onnx{suffix}"
)


# ---------------------------------------------------------------------------
# Text normalization + WER (stdlib only)
# ---------------------------------------------------------------------------


_UNITS = ["zero", "one", "two", "three", "four", "five", "six", "seven",
          "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen",
          "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
         "eighty", "ninety"]


def _num_to_words(n: int) -> str:
    """0–999; enough for the benchmark prompt/sentence sets."""
    if n < 20:
        return _UNITS[n]
    if n < 100:
        tens, rem = divmod(n, 10)
        return f"{_TENS[tens]} {_UNITS[rem]}" if rem else _TENS[tens]
    hundreds, rem = divmod(n, 100)
    out = f"{_UNITS[hundreds]} hundred"
    if rem:
        out += f" {_num_to_words(rem)}"
    return out


def _normalize(text: str) -> list[str]:
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    # Normalize digit tokens to words so "2:30 PM" == "two thirty pm" and
    # "512" == "five hundred (and) twelve" — WER should measure recognition
    # errors, not transcription formatting choices.
    words: list[str] = []
    for tok in text.split():
        if tok.isdigit() and int(tok) < 1000:
            words.extend(_num_to_words(int(tok)).split())
        else:
            words.append(tok)
    # Drop "and" — its optional use inside spoken numbers ("five hundred
    # and twelve") is a formatting difference, not a recognition error.
    words = [w for w in words if w != "and"]
    # Rejoin am/pm split apart by punctuation stripping ("p.m." -> "p m").
    out: list[str] = []
    i = 0
    while i < len(words):
        if i + 1 < len(words) and words[i] in ("a", "p") and words[i + 1] == "m":
            out.append(words[i] + "m")
            i += 2
        else:
            out.append(words[i])
            i += 1
    return out


def wer(reference: str, hypothesis: str) -> float:
    """Word error rate via Levenshtein on normalized word sequences."""
    ref = _normalize(reference)
    hyp = _normalize(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    # dp[j] = edit distance between ref[:i] and hyp[:j], rolling rows
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i] + [0] * len(hyp)
        for j, h in enumerate(hyp, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h))
        prev = cur
    return prev[-1] / len(ref)


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------


def _wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def _pcm_to_wav_bytes(pcm: bytes, sample_rate: int) -> bytes:
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + len(pcm), b"WAVE", b"fmt ",
        16, 1, 1, sample_rate, sample_rate * 2, 2, 16, b"data", len(pcm),
    )
    return header + pcm


# ---------------------------------------------------------------------------
# Piper voice download (voice files are not shipped with piper-tts)
# ---------------------------------------------------------------------------


def ensure_piper_voice(voice: str, cache_dir: Path) -> Path:
    """Return path to the voice .onnx, downloading from HF if missing."""
    onnx = cache_dir / f"{voice}.onnx"
    if onnx.exists():
        return onnx
    m = re.fullmatch(r"(en)_(US|GB)-([a-z]+)-(low|medium|high)", voice)
    if not m:
        raise SystemExit(f"cannot derive download URL for voice '{voice}'")
    lang, region, name, quality = m.group(1), m.group(2), m.group(3), m.group(4)
    cache_dir.mkdir(parents=True, exist_ok=True)
    for suffix in (".onnx", ".onnx.json"):
        url = PIPER_VOICE_URL.format(
            lang=lang, region=region, name=name, quality=quality,
            voice=voice, suffix=".json" if suffix == ".onnx.json" else "",
        )
        dest = cache_dir / f"{voice}{suffix}"
        print(f"downloading {url} -> {dest}", flush=True)
        urllib.request.urlretrieve(url, dest)
    return onnx


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------


def mode_prompts() -> None:
    print("Record each line as NN.<ext> (01.m4a … 12.m4a — wav/mp3/m4a all fine).")
    print("Name files with the two-digit prompt number; reference transcripts")
    print("are embedded in this script, so no manual transcription needed.\n")
    for i, p in enumerate(STT_PROMPTS, 1):
        print(f"{i:02d}. {p}")


def mode_stt(args: argparse.Namespace) -> None:
    from faster_whisper import WhisperModel
    from faster_whisper.audio import decode_audio

    audio_exts = {".wav", ".m4a", ".mp3", ".aac", ".caf", ".flac", ".ogg"}
    samples = sorted(p for p in args.samples_dir.iterdir()
                     if p.suffix.lower() in audio_exts)
    if not samples:
        raise SystemExit(
            f"no audio files in {args.samples_dir} (see 'prompts' mode)")

    t0 = time.monotonic()
    model = WhisperModel(
        args.model, device=args.device, compute_type=args.compute_type,
        device_index=args.device_index,
        download_root=str(args.model_cache_dir),
    )
    load_s = time.monotonic() - t0
    print(f"model load: {load_s:.1f}s ({args.model}, {args.device}/{args.compute_type})")

    rows = []
    for i, audio_path in enumerate(samples):
        idx = int(audio_path.stem[:2]) if audio_path.stem[:2].isdigit() else i + 1
        ref = STT_PROMPTS[idx - 1]
        # Decode via PyAV so m4a/mp3/etc. work without a manual ffmpeg step.
        audio = decode_audio(str(audio_path), sampling_rate=16000)
        dur = len(audio) / 16000
        t0 = time.monotonic()
        segments, _ = model.transcribe(
            audio, language=args.language,
            beam_size=args.beam_size, vad_filter=True,
        )
        hyp = " ".join(s.text for s in segments).strip()
        elapsed = time.monotonic() - t0
        w = wer(ref, hyp)
        rtf = dur / elapsed if elapsed else 0.0
        rows.append({"file": audio_path.name, "dur": dur, "elapsed": elapsed,
                     "rtf": rtf, "wer": w, "hyp": hyp})
        flag = "" if w == 0 else "  <-- check"
        print(f"{audio_path.name}: {dur:.1f}s audio in {elapsed:.2f}s "
              f"(RTF {rtf:.1f}x)  WER {w:.1%}{flag}")
        if w > 0:
            print(f"   ref: {ref}\n   hyp: {hyp}")

    _report(args, rows, load_s)


def _load_piper_tts(args: argparse.Namespace) -> tuple[object, int]:
    from piper import PiperVoice

    onnx = ensure_piper_voice(args.tts_voice, args.model_cache_dir)
    t0 = time.monotonic()
    tts = PiperVoice.load(str(onnx))
    print(f"voice load: {time.monotonic() - t0:.1f}s ({args.tts_voice})")
    return tts, tts.config.sample_rate


def _load_kokoro_tts(args: argparse.Namespace) -> tuple[object, int]:
    from kokoro import KPipeline

    lang_code = args.tts_voice[0] if args.tts_voice else "a"
    t0 = time.monotonic()
    pipeline = KPipeline(lang_code=lang_code)
    print(f"voice load: {time.monotonic() - t0:.1f}s (kokoro {args.tts_voice})")
    return pipeline, args.tts_sample_rate


def _synthesize_kokoro_sentence(tts: object, text: str, voice: str) -> bytes:
    import numpy as np

    pcm_chunks: list[bytes] = []
    for _gs, _ps, audio in tts(text, voice=voice, speed=1.0, split_pattern=r"\n+"):
        arr = np.asarray(audio)
        pcm_chunks.append((arr * 32767).astype(np.int16).tobytes())
    return b"".join(pcm_chunks)


def mode_tts(args: argparse.Namespace) -> None:
    if args.tts_engine == "piper":
        tts, sample_rate = _load_piper_tts(args)
    elif args.tts_engine == "kokoro":
        tts, sample_rate = _load_kokoro_tts(args)
    else:
        raise SystemExit(f"unsupported TTS engine: {args.tts_engine}")

    ref_stt = None
    if args.roundtrip_stt:
        from faster_whisper import WhisperModel
        t0 = time.monotonic()
        ref_stt = WhisperModel(
            args.roundtrip_stt, device=args.device,
            compute_type=args.compute_type,
            download_root=str(args.model_cache_dir),
        )
        print(f"round-trip STT load: {time.monotonic() - t0:.1f}s ({args.roundtrip_stt})")

    out_dir = args.out_dir / args.label
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for i, text in enumerate(TTS_SENTENCES, 1):
        t0 = time.monotonic()
        if args.tts_engine == "piper":
            pcm = b"".join(c.audio_int16_bytes for c in tts.synthesize(text))
        else:
            pcm = _synthesize_kokoro_sentence(tts, text, args.tts_voice)
        elapsed = time.monotonic() - t0
        wav_bytes = _pcm_to_wav_bytes(pcm, sample_rate)
        wav_path = out_dir / f"{i:02d}.wav"
        wav_path.write_bytes(wav_bytes)
        dur = len(pcm) / 2 / sample_rate
        rtf = dur / elapsed if elapsed else 0.0
        w = -1.0
        hyp = ""
        if ref_stt is not None:
            segments, _ = ref_stt.transcribe(
                io.BytesIO(wav_bytes), language=args.language,
                beam_size=args.beam_size, vad_filter=False,
            )
            hyp = " ".join(s.text for s in segments).strip()
            w = wer(text, hyp)
        rows.append({"file": wav_path.name, "dur": dur, "elapsed": elapsed,
                     "rtf": rtf, "wer": w, "hyp": hyp})
        wer_str = f"  roundtrip-WER {w:.1%}" if w >= 0 else ""
        print(f"{i:02d}: {dur:.1f}s audio in {elapsed:.2f}s (RTF {rtf:.1f}x){wer_str}")
        if 0 < w and ref_stt is not None:
            print(f"   ref: {text}\n   hyp: {hyp}")

    print(f"\nWAVs written to {out_dir} — listen and rate naturalness 1–5.")
    _report(args, rows, load_s=0.0)


def _report(args: argparse.Namespace, rows: list[dict], load_s: float) -> None:
    rtfs = [r["rtf"] for r in rows]
    wers = [r["wer"] for r in rows if r["wer"] >= 0]
    lat = [r["elapsed"] for r in rows]
    med_rtf = statistics.median(rtfs)
    med_lat = statistics.median(lat)
    mean_wer = statistics.mean(wers) if wers else -1.0
    print(f"\n[{args.label}] median RTF {med_rtf:.1f}x  median latency {med_lat:.2f}s"
          + (f"  mean WER {mean_wer:.1%}" if wers else ""))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    new = not args.out.exists()
    with args.out.open("a", newline="") as f:
        wcsv = csv.DictWriter(f, fieldnames=[
            "ts", "mode", "label", "model", "device", "compute_type",
            "n", "load_s", "median_rtf", "median_latency_s", "mean_wer",
        ])
        if new:
            wcsv.writeheader()
        wcsv.writerow({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "mode": args.mode,
            "label": args.label,
            "model": args.model if args.mode == "stt" else args.tts_voice,
            "device": args.device,
            "compute_type": args.compute_type,
            "n": len(rows),
            "load_s": round(load_s, 2),
            "median_rtf": round(med_rtf, 2),
            "median_latency_s": round(med_lat, 3),
            "mean_wer": round(mean_wer, 4) if wers else "",
        })


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["prompts", "stt", "tts"])
    ap.add_argument("--label", default="")
    ap.add_argument("--samples-dir", type=Path,
                    default=Path("runtime-data/bench/voice-samples"))
    ap.add_argument("--out-dir", type=Path,
                    default=Path("runtime-data/bench/voice-tts-out"))
    ap.add_argument("--out", type=Path,
                    default=Path("runtime-data/bench/voice-bench.csv"))
    ap.add_argument("--model-cache-dir", type=Path,
                    default=Path.home() / ".cache" / "hestia" / "voice")
    # STT options (defaults mirror config.runtime.py)
    ap.add_argument("--model", default="medium")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--device-index", type=int, default=0,
                    help="GPU index when --device cuda (default 0)")
    ap.add_argument("--compute-type", default="int8")
    ap.add_argument("--language", default="en")
    ap.add_argument("--beam-size", type=int, default=5)
    # TTS options
    ap.add_argument("--tts-engine", default="piper",
                    choices=["piper", "kokoro"],
                    help="TTS backend (default: piper)")
    ap.add_argument("--tts-voice", default="en_US-amy-medium")
    ap.add_argument("--tts-sample-rate", type=int, default=22050,
                    help="output sample rate for TTS audio (default: 22050)")
    ap.add_argument("--roundtrip-stt", default=None,
                    help="reference STT model for TTS intelligibility WER")
    args = ap.parse_args()

    if args.mode != "prompts" and not args.label:
        ap.error("--label is required for stt/tts modes")

    if args.mode == "prompts":
        mode_prompts()
    elif args.mode == "stt":
        mode_stt(args)
    else:
        mode_tts(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
