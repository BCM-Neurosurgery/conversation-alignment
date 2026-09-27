#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
STEP 1 of 4 — .wav -> words + speakers, with WhisperX.

WhisperX = Whisper transcription + a wav2vec2 forced-alignment pass for word times + (optionally) pyannote
diarization for who-spoke-when. This step gives you the WORDS and a first guess at the SPEAKERS.
Its word onsets are good enough to align from, but NOT good enough to analyse — on our room-mic recordings they
run ~65 ms late. Step 3 (MFA) is what fixes that. Do not skip it.

    python step1_whisper.py <audio.wav> <out_dir> [--model large-v3] [--max-speakers 5] [--no-diarize]

Outputs in <out_dir>:
    <stem>.words.csv     word,start,end,speaker   (seconds)  <- step 2 reads this
    <stem>.whisperx.json  full WhisperX output (segments + words), for reference

Diarization needs a HuggingFace token (accept the pyannote model terms once, then `huggingface-cli login`,
or put the token in ~/.cache/huggingface/token). Without it, run --no-diarize and everything lands on one
speaker, which is fine for single-speaker audio.
"""
from __future__ import annotations
import argparse, csv, json, os, sys
from pathlib import Path


def hf_token():
    for v in ("HUGGINGFACE_TOKEN", "HF_TOKEN"):
        if os.environ.get(v):
            return os.environ[v].strip()
    p = Path.home() / ".cache" / "huggingface" / "token"
    return p.read_text().strip() if p.exists() else None


def load_model(name, dev):
    import whisperx
    if dev == "cpu":
        m = whisperx.load_model(name, dev, compute_type="int8")
        print(f"  [whisper] {name} on cpu (compute_type=int8)")   # same line the GPU path prints, so the
        return m                                                  # SOP's "what you should see" holds on a Mac
    for ct in ("float16", "int8_float16", "int8"):
        try:
            m = whisperx.load_model(name, dev, compute_type=ct)
            print(f"  [whisper] {name} on {dev} (compute_type={ct})")
            return m
        except Exception as e:
            print(f"  compute_type={ct} failed: {type(e).__name__}")
    raise RuntimeError(f"could not load {name} on {dev}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("wav"); ap.add_argument("out_dir")
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--language", default="en")
    ap.add_argument("--max-speakers", type=int, default=5)
    ap.add_argument("--min-speakers", type=int, default=1)
    ap.add_argument("--no-diarize", action="store_true")
    ap.add_argument("--device", default=None)
    a = ap.parse_args()

    import torch, whisperx
    dev = a.device or ("cuda" if torch.cuda.is_available() else "cpu")
    out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
    stem = Path(a.wav).stem

    audio = whisperx.load_audio(str(a.wav))
    model = load_model(a.model, dev)
    # condition_on_previous_text=False: stops one bad segment from derailing the rest of a long recording
    res = model.transcribe(audio, language=a.language, batch_size=8,
                           print_progress=True, chunk_size=20)
    print(f"  [whisper] {len(res['segments'])} segments")

    align_model, meta = whisperx.load_align_model(language_code=a.language, device=dev)
    res = whisperx.align(res["segments"], align_model, meta, audio, dev, return_char_alignments=False)
    print(f"  [align] word times from wav2vec2")

    if not a.no_diarize:
        tok = hf_token()
        if not tok:
            print("  [diarize] SKIPPED — no HuggingFace token (see the docstring). All words -> SPEAKER_00")
        else:
            # Diarization is the one optional stage: the pyannote models are GATED (you must accept their terms
            # on huggingface.co once, for BOTH pyannote/segmentation-3.0 and pyannote/speaker-diarization-3.1).
            # If that has not been done, keep the words rather than losing the whole run.
            from whisperx.diarize import DiarizationPipeline
            diar = None
            for device in ([dev, "cpu"] if dev != "cpu" else ["cpu"]):
                try:
                    pipe = DiarizationPipeline(model_name="pyannote/speaker-diarization-3.1", token=tok, device=device)
                    diar = pipe(str(a.wav), min_speakers=a.min_speakers, max_speakers=a.max_speakers)
                    break
                except Exception as e:
                    msg = f"{type(e).__name__}: {e}"
                    if "GatedRepo" in msg or "403" in msg or "restricted" in msg:
                        print("  [diarize] SKIPPED — your HuggingFace account has not been granted access to\n"
                              "            pyannote/speaker-diarization-3.1. Accept the terms at\n"
                              "            https://huggingface.co/pyannote/speaker-diarization-3.1 (and\n"
                              "            .../pyannote/segmentation-3.0), then re-run. All words -> SPEAKER_00.")
                        break
                    print(f"  [diarize] {device} failed ({msg.splitlines()[0][:120]})")
            if diar is not None:
                res = whisperx.assign_word_speakers(diar, res)
                print("  [diarize] speakers assigned")

    (out / f"{stem}.whisperx.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    rows, n_nospk = [], 0
    for seg in res["segments"]:
        for w in seg.get("words", []):
            if w.get("start") is None or w.get("end") is None:
                continue                                    # unaligned word (no acoustic anchor) — dropped
            spk = w.get("speaker") or seg.get("speaker") or "SPEAKER_00"
            if not w.get("speaker"):
                n_nospk += 1
            rows.append((str(w["word"]).strip(), round(float(w["start"]), 3), round(float(w["end"]), 3), spk))
    rows.sort(key=lambda r: r[1])
    with open(out / f"{stem}.words.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f); wr.writerow(["word", "start", "end", "speaker"]); wr.writerows(rows)
    spk = sorted({r[3] for r in rows})
    print(f"[done] {len(rows)} words, speakers {spk} ({n_nospk} words inherited their segment's speaker)")
    print(f"       -> {out / (stem + '.words.csv')}")


if __name__ == "__main__":
    main()
