#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Is this computer ready to run the pipeline? Answers in plain English, and says what to do about anything missing.

    python check_setup.py

Run it from anywhere, in any environment — it looks into the two conda environments itself.
"""
from __future__ import annotations
import shutil, subprocess, sys


def line(mark, label, msg):
    """One aligned result row: [ok] / [X] / [--], a fixed-width label, then plain English."""
    print(f"  [{mark:>2}] {label:<12} {msg}")


def sh(cmd, timeout=180):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr)
    except Exception as e:
        return 1, f"{type(e).__name__}: {e}"


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("\nChecking your setup. This takes about half a minute.\n")
    problems = []

    conda = shutil.which("conda")
    if not conda:
        line("X", "conda", "not found")
        print("\nNothing else can be checked without it.")
        print("On Windows, open 'Anaconda Prompt' from the Start menu and run this again there.")
        print("On a Mac, quit Terminal completely and reopen it. If it still says this, install Miniconda:")
        print("  https://docs.conda.io/en/latest/miniconda.html")
        return 1
    line("ok", "conda", conda)

    _, listed = sh([conda, "env", "list"])
    names = {ln.split()[0] for ln in listed.splitlines() if ln.strip() and not ln.startswith("#")}

    # 1. transcription
    if "whisper" not in names:
        line("X", "whisper env", "missing")
        problems.append("conda env create -f environment_whisper.yml")
    else:
        code, out = sh([conda, "run", "-n", "whisper", "python", "-c",
                        "import whisperx, pandas, praatio, openpyxl; print('ok')"])
        if code == 0 and "ok" in out:
            line("ok", "whisper env", "transcription libraries load")
        else:
            line("X", "whisper env", "exists, but its libraries do not load")
            print("       " + out.strip().splitlines()[-1][:110] if out.strip() else "")
            problems.append("conda env update -f environment_whisper.yml --prune")
        if shutil.which("ffmpeg") or sh([conda, "run", "-n", "whisper", "ffmpeg", "-version"])[0] == 0:
            line("ok", "ffmpeg", "present")
        else:
            line("X", "ffmpeg", "missing - whisperx cannot read audio without it")
            problems.append("conda install -n whisper -c conda-forge ffmpeg")

    # 2. the aligner
    env_mfa = next((e for e in ("mfa2", "mfa") if e in names), None)
    if not env_mfa:
        line("X", "mfa2 env", "missing")
        problems.append("conda env create -f environment_mfa.yml")
    else:
        code, out = sh([conda, "run", "-n", env_mfa, "mfa", "version"])
        ver = next((l.strip() for l in out.splitlines() if l.strip() and l.strip()[0].isdigit()), "?")
        line("ok" if code == 0 else "X", f"{env_mfa} env", f"aligner version {ver}")
        if code:
            problems.append("conda env create -f environment_mfa.yml")
        else:
            _, models = sh([conda, "run", "-n", env_mfa, "mfa", "model", "list", "acoustic"])
            if "english_us_arpa" in models:
                line("ok", "language", "english_us_arpa models downloaded")
            else:
                line("X", "language", "english_us_arpa models not downloaded")
                problems += [f"conda run -n {env_mfa} mfa model download {k} english_us_arpa"
                             for k in ("acoustic", "dictionary", "g2p")]

    # 3. optional: can it tell the speakers apart?
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
    try:
        from step1_whisper import hf_token
        ok = hf_token() is not None
    except Exception:
        ok = False
    line("ok" if ok else "--", "speakers",
         "HuggingFace sign-in found" if ok else
         "no sign-in - every word lands on one row (optional; see the guide)")

    print()
    if problems:
        print("Not ready yet. Run these, in this order:\n")
        for p in problems:
            print("    " + p)
        print("\nThen run this check again.")
        return 1
    print("Ready. Transcribe a recording with:  python run_all.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
