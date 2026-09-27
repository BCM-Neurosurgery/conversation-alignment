#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
STEP 3 of 4 — run the Montreal Forced Aligner on the corpus step 2 built.

Same job as `step3_mfa_align.sh`, but plain Python so it runs in the Anaconda Prompt on Windows, where there is
no `bash`. (The .sh version stays for the lab cluster.)

    conda activate mfa2
    python step3_mfa_align.py <corpus_dir> <output_dir>

This is the step that makes the timings trustworthy: Whisper's word starts run ~65 ms late on room-mic audio,
MFA's do not.

Notes kept from painful experience:
- MFA 3.1.0 is the version that works (conda-forge >= 3.2 pins a kalpy that lacks G2PCompiler).
- Noisy conversation audio needs a wider search or whole utterances silently fail to align — that comes from
  align_config.yaml (beam 100 / retry_beam 400); MFA 3.1 has no --beam flag.
- The alignment you want is in MFA's database, not only the exported TextGrids (MFA 3.1 drops the first word of
  each utterance on export). Step 4 finds the database itself.
"""
from __future__ import annotations
import argparse, shutil, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(cmd, check=True, quiet=False):
    if not quiet:
        print(f"\n$ {' '.join(str(c) for c in cmd)}", flush=True)
    r = subprocess.run([str(c) for c in cmd], capture_output=quiet, text=True)
    if check and r.returncode:
        raise SystemExit(f"\nthat command failed (exit {r.returncode}).\n"
                         f"Copy the lines above and send them to whoever gave you this folder.")
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("corpus_dir"); ap.add_argument("output_dir")
    ap.add_argument("--dictionary", default="english_us_arpa")
    ap.add_argument("--acoustic", default="english_us_arpa")
    ap.add_argument("--g2p", default="english_us_arpa", help="pronounces names/acronyms MFA doesn't know; '' to skip")
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()

    if not shutil.which("mfa"):
        raise SystemExit("'mfa' was not found.\n"
                         "You are probably in the wrong environment — run:  conda activate mfa2\n"
                         "(and if that fails, the environment was never made: see the setup steps in the guide)")

    corpus, out = Path(a.corpus_dir).resolve(), Path(a.output_dir).resolve()
    if not corpus.is_dir():
        raise SystemExit(f"no such folder: {corpus}")

    for kind, name in (("acoustic", a.acoustic), ("dictionary", a.dictionary), ("g2p", a.g2p)):
        if name:
            run(["mfa", "model", "download", kind, name], check=False, quiet=True)

    run(["mfa", "server", "stop"], check=False, quiet=True)          # a clean database server each run
    time.sleep(2)
    if run(["mfa", "server", "start"], check=False).returncode:
        run(["mfa", "server", "init"], check=False)
        run(["mfa", "server", "start"], check=False)
    time.sleep(2)

    if out.exists():
        shutil.rmtree(out)
    cmd = ["mfa", "align", "--clean", "-j", a.jobs, "--output_format", "long_textgrid"]
    cfg = HERE / "align_config.yaml"
    if cfg.exists():
        cmd += ["--config_path", cfg]
    if a.g2p:
        cmd += ["--g2p_model_path", a.g2p]
    cmd += [corpus, a.dictionary, a.acoustic, out]
    t0 = time.time()
    run(cmd)
    run(["mfa", "server", "stop"], check=False, quiet=True)

    print(f"\n[done] MFA finished in {time.time() - t0:.0f}s -> {out}")
    print("Next:  python step4_textgrid.py "
          f"\"{corpus / (corpus.name + '.sidecar.json')}\" \"{out.parent}\"")
    print("       (step 4 finds MFA's database on its own; if the sidecar name above looks wrong, use the\n"
          "        .sidecar.json file that is actually inside your 02_mfa_corpus folder)")


if __name__ == "__main__":
    main()
