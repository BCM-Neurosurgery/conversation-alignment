#!/bin/bash
# STEP 3 of 4 — run the Montreal Forced Aligner on the corpus built by step 2.
#
# This is the step that makes the timings trustworthy: Whisper's word onsets run ~65 ms late on room-mic
# audio, MFA's do not. Everything before this is words; this is timing.
#
#   bash step3_mfa_align.sh <corpus_dir> <output_dir>
#
# Works two ways:
#   A. LOCALLY, if you have MFA in a conda env (see README):  conda activate mfa2 && bash step3_mfa_align.sh ...
#   B. On the lab cluster (wrangell), submitted with sbatch — see the SLURM block at the bottom.
#
# Notes
# - MFA 3.1.0 is the version the lab has working (conda-forge >= 3.2 is broken: it pins a kalpy that lacks
#   G2PCompiler). Pin joblib=1.4.2 and setuptools<81 alongside it.
# - --g2p_model_path lets MFA invent a pronunciation for out-of-vocabulary words (names, "AFOs", numbers)
#   instead of failing or skipping them.
# - Noisy conversation audio needs a wider search than MFA's default or whole utterances fail to align
#   (align_config.yaml: beam 100 / retry_beam 400). MFA 3.1 has NO --beam CLI flag, it must come from the
#   config file, which this script passes automatically.
# - MFA runs one job per SPEAKER, so a corpus with a speaker that has almost no words will crash. Step 2
#   already drops those.
# - The alignment you want is in MFA's database (~/Documents/MFA/<corpus>/<corpus>.db), not only in
#   the exported TextGrids — step 4 finds it automatically.
set -e
CORPUS="${1:?usage: step3_mfa_align.sh <corpus_dir> <output_dir>}"
OUT="${2:?usage: step3_mfa_align.sh <corpus_dir> <output_dir>}"
DICT="${MFA_DICT:-english_us_arpa}"
ACOUSTIC="${MFA_ACOUSTIC:-english_us_arpa}"
G2P="${MFA_G2P:-}"                 # optional: path to english_us_arpa.zip g2p model
JOBS="${MFA_JOBS:-8}"
CONFIG="${MFA_CONFIG:-$(dirname "$0")/align_config.yaml}"   # wider beam: noisy room audio needs it

command -v mfa >/dev/null || { echo "ERROR: 'mfa' not on PATH — activate the MFA conda env first"; exit 1; }

# one-time (no-ops if already there):
mfa model download acoustic "$ACOUSTIC" 2>/dev/null || true
mfa model download dictionary "$DICT" 2>/dev/null || true

# MFA keeps its working database in a postgres server it manages itself; restart it clean each run.
mfa server stop 2>/dev/null || true
sleep 2
mfa server start || { mfa server init && mfa server start; }
sleep 2

rm -rf "$OUT"
ARGS=(--clean -j "$JOBS" --output_format long_textgrid)
[ -n "$G2P" ] && ARGS+=(--g2p_model_path "$G2P")
[ -f "$CONFIG" ] && ARGS+=(--config_path "$CONFIG")
mfa align "${ARGS[@]}" "$CORPUS" "$DICT" "$ACOUSTIC" "$OUT"

mfa server stop 2>/dev/null || true
echo "MFA done -> $OUT"
echo "database (what step 4 reads):  ~/Documents/MFA/$(basename "$CORPUS")/$(basename "$CORPUS").db"

# ---------------------------------------------------------------------------------------------------
# SLURM version for the lab cluster — save as a separate file and `sbatch` it:
#
# #!/bin/bash
# #SBATCH --job-name=mfa_align
# #SBATCH --partition=chipmunk          # CPU-only is fine; MFA does not use the GPU
# #SBATCH --cpus-per-task=32
# #SBATCH --mem=96G
# #SBATCH --time=02:00:00
# #SBATCH --qos=default_tier
# #SBATCH --output=logs/mfa_%j.out
# source /path/to/miniforge3/etc/profile.d/conda.sh
# conda activate mfa2
# export MFA_JOBS=32
# bash step3_mfa_align.sh /path/to/corpus /path/to/out
#
# Submit with `sbatch`, never `srun` (interactive srun hangs on this cluster).
# Align several recordings SEQUENTIALLY in one job: concurrent MFA runs share one postgres server and conflict.
