#!/bin/bash
# One-time setup, macOS. In Terminal:
#     cd "the folder this file is in"
#     bash setup_mac.sh
# It builds both conda environments and downloads the aligner's English models. 30-45 minutes, mostly waiting.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"

echo
echo "============================================================"
echo "  Conversation pipeline - one-time setup"
echo "============================================================"
echo

if ! command -v conda >/dev/null 2>&1; then
  echo "I cannot find conda, so I cannot set anything up."
  echo
  echo "If you just installed Miniconda, quit Terminal completely (Cmd+Q) and open"
  echo "it again - the installer only changes windows opened after it ran."
  echo
  echo "If you have not installed it yet:"
  echo "    https://docs.conda.io/en/latest/miniconda.html"
  echo "Choose the Apple Silicon build if 'About This Mac' says M1/M2/M3, the Intel build otherwise."
  echo
  exit 1
fi

# Apple Silicon has no conda-forge build of MFA 3.1.0; build that one env as Intel and let Rosetta run it.
MFA_PREFIX=""
if [ "$(uname -m)" = "arm64" ]; then
  echo "Apple Silicon detected - the aligner will be installed as Intel and run under Rosetta."
  MFA_PREFIX="CONDA_SUBDIR=osx-64"
fi

echo "[1 of 3] Building the transcription environment."
echo "         Several gigabytes. Leave it alone; it is not stuck."
echo
conda env create -f "$HERE/environment_whisper.yml" \
  || { echo; echo '  "whisper" already exists - updating it instead.'; \
       conda env update -f "$HERE/environment_whisper.yml" --prune; }

echo
echo "[2 of 3] Building the aligner environment."
echo
env $MFA_PREFIX conda env create -f "$HERE/environment_mfa.yml" \
  || { echo; echo '  "mfa2" already exists - updating it instead.'; \
       env $MFA_PREFIX conda env update -f "$HERE/environment_mfa.yml" --prune; }
if [ -n "$MFA_PREFIX" ]; then
  conda config --env --set subdir osx-64 2>/dev/null || true
fi

echo
echo "[3 of 3] Downloading the aligner's English models."
echo
for kind in acoustic dictionary g2p; do
  conda run -n mfa2 --no-capture-output mfa model download "$kind" english_us_arpa
done

echo
echo "============================================================"
echo "  Checking it all worked"
echo "============================================================"
conda run -n whisper --no-capture-output python "$HERE/check_setup.py"

echo
echo "If the check above says \"Ready\", you are done. To transcribe a recording:"
echo
echo "    conda activate whisper"
echo "    cd \"$HERE\""
echo "    python run_all.py"
echo
