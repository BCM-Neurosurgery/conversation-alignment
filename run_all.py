#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Run the whole thing: .wav -> Whisper -> MFA -> word TextGrid + Excel.

The easy way — type this and answer the questions:

    python run_all.py

The exact way, if you already know the answers:

    python run_all.py <audio.wav> <out_dir> [--speakers 3] [--model large-v3] [--skip-mfa]

`--speakers N` is for when you KNOW how many people are in the room: it makes the speaker-splitter find exactly
N. Leave it off and it guesses (at most `--max-speakers`, default 5). Guessing is the thing this pipeline gets
wrong most often, so answer it if you can.

If MFA is not installed here, steps 1-2 still run and the script prints exactly what to run on the cluster
(or in your MFA env) and how to finish with step 4. Nothing is overwritten: everything lands in <out_dir>.

Layout produced:
    <out_dir>/01_whisper/<stem>.words.csv        words + speaker guess
    <out_dir>/02_mfa_corpus/<stem>.{wav,TextGrid,sidecar.json}
    <out_dir>/03_mfa_out/                        MFA's own output
    <out_dir>/<stem>_words.TextGrid              <- open in Praat with the wav
    <out_dir>/<stem>_words.xlsx                  <- the lab word table
"""
from __future__ import annotations
import argparse, re, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUDIO_EXT = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aif", ".aiff", ".wma", ".mp4"}


def run(cmd, **kw):
    print(f"\n$ {' '.join(str(c) for c in cmd)}", flush=True)
    r = subprocess.run([str(c) for c in cmd], **kw)
    if r.returncode:
        raise SystemExit(f"step failed ({r.returncode}): {cmd[1] if len(cmd) > 1 else cmd}")


# ----------------------------------------------------------------------------- the questions
# Undergrads run this. Assume the path was DRAGGED into the window, not typed: Windows "Copy as path" wraps it in
# quotes, macOS Terminal backslash-escapes every space. Both must just work.
def clean_path(raw: str) -> str:
    s = raw.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        s = s[1:-1].strip()
    if s.startswith(("/", "~")):                      # a POSIX path: undo Terminal's drag-and-drop escaping
        s = re.sub(r"\\(.)", r"\1", s)
    return s


def ask(prompt: str) -> str:
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        raise SystemExit("\nstopped. Nothing was changed.")


def ask_audio() -> Path:
    print("\n1) THE RECORDING")
    print("   Drag the sound file into this window and press Enter (or paste its path).")
    while True:
        p = Path(clean_path(ask("   > "))).expanduser()
        if str(p) in ("", "."):
            print("   I need a file to work on. Drag it in, then press Enter.")
        elif p.is_dir():
            print(f"   That is a folder, not a recording. Open it and drag the sound file itself in.")
        elif not p.exists():
            print(f"   I cannot find that: {p}")
            print("   Drag the file into this window rather than typing the path.")
        elif p.suffix.lower() not in AUDIO_EXT:
            print(f"   That is a {p.suffix or 'nameless'} file, not audio. I expect a .wav.")
        else:
            return p.resolve()


def ask_out(default: Path) -> Path:
    print("\n2) WHERE THE RESULTS SHOULD GO")
    print(f"   Press Enter to use:  {default}")
    raw = clean_path(ask("   > "))
    return (Path(raw).expanduser().resolve() if raw else default)


def mfa_runner():
    """How do we reach MFA: in this environment, in the one next door, or not at all?

    Annotators used to have to stop here, switch conda environment by hand and paste two commands — the single
    most confusing moment in the whole pipeline. `conda run` does it for them without leaving this one.
    Returns the command prefix that runs step 3, or None.
    """
    if shutil.which("mfa"):
        return [sys.executable, HERE / "step3_mfa_align.py"], None
    conda = shutil.which("conda")
    if not conda:
        return None, None
    try:
        listed = subprocess.run([conda, "env", "list"], capture_output=True, text=True, timeout=120).stdout
    except Exception:
        return None, None
    names = {ln.split()[0] for ln in listed.splitlines() if ln.strip() and not ln.startswith("#")}
    for env in ("mfa2", "mfa"):
        if env in names:
            return [conda, "run", "-n", env, "--no-capture-output",
                    "python", HERE / "step3_mfa_align.py"], env
    return None, None


def hf_ready() -> bool:
    """Is speaker-splitting actually available? Reuse step 1's rule rather than inventing a second one."""
    try:
        sys.path.insert(0, str(HERE))
        from step1_whisper import hf_token
        return hf_token() is not None
    except Exception:
        return False


def ask_speakers() -> int | None:
    """None = let the code guess. Otherwise an exact headcount."""
    print("\n3) HOW MANY PEOPLE ARE TALKING IN THIS RECORDING?")
    print("   Count everyone whose voice is on the tape: the patient, the person asking questions,")
    print("   anyone else in the room who says more than a few words.")
    print("   Type a number (2, 3, 4 ...) if you know it, or press Enter to let the code guess.")
    while True:
        raw = ask("   > ").strip()
        if not raw:
            print("   OK - I will guess (no more than 5). Check the speaker rows carefully in Praat.")
            return None
        if raw.isdigit() and 1 <= int(raw) <= 20:
            n = int(raw)
            print(f"   OK - I will split the recording into exactly {n} speaker{'s' if n > 1 else ''}.")
            return n
        print("   Please type a whole number between 1 and 20, or just press Enter.")


def wizard(a):
    """Fill in whatever was not given on the command line. Only ever runs at a real keyboard."""
    print("=" * 74)
    print("  RECORDING  ->  TRANSCRIPT       answer a few questions, then leave it alone")
    print("=" * 74)
    wav = Path(a.wav).expanduser().resolve() if a.wav else ask_audio()
    out = (Path(a.out_dir).expanduser().resolve() if a.out_dir
           else ask_out(wav.parent / f"{wav.stem}_out"))
    n = a.speakers if a.speakers else ask_speakers()

    # Telling them now beats them discovering it after the transcript comes back on one row.
    if (n is None or n > 1) and not a.no_diarize and not hf_ready():
        print("\n   NOTE: splitting the speakers apart needs the one-time HuggingFace sign-in from the setup")
        print("   instructions, and it is not set up on this computer. Every word will land on ONE row and")
        print("   you separate the speakers yourself in Praat. That works fine - it is just more clicking.")

    print("\n" + "-" * 74)
    print(f"  recording : {wav}")
    print(f"  results   : {out}")
    print(f"  speakers  : {n if n else 'guess (up to %d)' % a.max_speakers}")
    flag = f" --speakers {n}" if n else ""
    print(f'\n  Next time you can skip the questions with:\n'
          f'    python run_all.py "{wav}" "{out}"{flag}')
    print("-" * 74)
    return wav, out, n


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("wav", nargs="?"); ap.add_argument("out_dir", nargs="?")
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--speakers", type=int, default=None,
                    help="exact number of people talking, when you know it (best answer)")
    ap.add_argument("--max-speakers", type=int, default=5, help="upper bound when --speakers is not given")
    ap.add_argument("--no-diarize", action="store_true")
    ap.add_argument("--no-ask", action="store_true", help="never prompt (for scripts and cluster jobs)")
    ap.add_argument("--skip-whisper", action="store_true", help="reuse 01_whisper/<stem>.words.csv")
    ap.add_argument("--skip-mfa", action="store_true", help="build the corpus, run MFA yourself, then step 4")
    a = ap.parse_args()

    interactive = sys.stdin is not None and sys.stdin.isatty() and not a.no_ask
    if not (a.wav and a.out_dir) or (a.speakers is None and not a.no_diarize and interactive):
        if not interactive:
            ap.error("give me <audio.wav> and <out_dir> (or run it without arguments to be asked)")
        wav, out, n_speakers = wizard(a)
    else:
        wav, out, n_speakers = Path(a.wav).resolve(), Path(a.out_dir).resolve(), a.speakers

    out.mkdir(parents=True, exist_ok=True)
    stem = wav.stem
    d1, d2, d3 = out / "01_whisper", out / "02_mfa_corpus", out / "03_mfa_out"

    # An exact headcount pins the splitter to that many voices; one speaker means there is nothing to split.
    lo, hi = (n_speakers, n_speakers) if n_speakers else (1, a.max_speakers)
    solo = a.no_diarize or n_speakers == 1

    if not a.skip_whisper:
        cmd = [sys.executable, HERE / "step1_whisper.py", wav, d1, "--model", a.model,
               "--min-speakers", lo, "--max-speakers", hi]
        if solo:
            cmd.append("--no-diarize")
        run(cmd)
    words_csv = d1 / f"{stem}.words.csv"
    if not words_csv.exists():
        raise SystemExit(f"missing {words_csv}")

    run([sys.executable, HERE / "step2_mfa_corpus.py", wav, words_csv, d2])

    step3, env = (None, None) if a.skip_mfa else mfa_runner()
    if step3 is None:
        print(f"""
--------------------------------------------------------------------------
MFA not run here ({'--skip-mfa' if a.skip_mfa else "no mfa2 environment found, and 'mfa' is not on PATH"}).
Run step 3 where MFA lives (lab cluster, or a local conda env - see README):

    conda activate mfa2
    python step3_mfa_align.py "{d2}" "{d3}"

then finish with:

    python step4_textgrid.py "{d2 / (stem + '.sidecar.json')}" "{out}"
--------------------------------------------------------------------------""")
        return

    if env:
        print(f"\n[mfa ] using the '{env}' environment - you do not need to switch to it yourself")
    run(step3 + [d2, d3])
    cmd = [sys.executable, HERE / "step4_textgrid.py", d2 / f"{stem}.sidecar.json", out]
    if not sorted((Path.home() / "Documents" / "MFA").glob(f"{d2.name}/*.db")):
        cmd += ["--mfa-out", d3]          # no database found; fall back to MFA's exported TextGrids
    run(cmd)
    print(f"\nDone. Open these two together in Praat and clean the transcript (see the SOP):"
          f"\n    {wav}\n    {out / (stem + '_words.TextGrid')}")


if __name__ == "__main__":
    main()
