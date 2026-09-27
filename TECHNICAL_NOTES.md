# convo `.wav` → word `.TextGrid` (Whisper → MFA)

Turns a conversation recording into a word-level TextGrid (and the lab's Excel word table) that a human then
cleans in Praat. Two machine stages, in this order:

```
   audio.wav
      │
      ├─ 1. WHISPER (WhisperX)   what was said, who said it, rough word times
      │        ↓  words.csv
      ├─ 2. MFA (forced aligner) re-aligns those words to the audio -> trustworthy word ONSETS
      │        ↓  alignment
      ├─ 3. (this package)       puts it back together
      │        ↓
      └─ <stem>_words.TextGrid + <stem>_words.xlsx   →  4. PRAAT: a human cleans it
```

**Why MFA is not optional.** Whisper's word onsets run **~65 ms late** on room-mic recordings — measured across
our conversations against two independent forced aligners. MFA removes that. Skipping it means a human
hand-correcting a systematic error on every word. (In one file that step was skipped and two-thirds of its word
onsets had to be corrected after the fact.)

Hand-cleaning afterwards is still required: see `SOP_Convo_Praat_Cleaning.md`.

---

## Install

**A. Whisper (step 1)** — any Python 3.10+ environment with a GPU if you have one:
```bash
pip install whisperx soundfile pandas praatio openpyxl
```
Diarization ("who spoke") additionally needs a free HuggingFace account:
1. accept the terms on **both** https://huggingface.co/pyannote/segmentation-3.0 and
   https://huggingface.co/pyannote/speaker-diarization-3.1
2. `huggingface-cli login` (or put the token in `~/.cache/huggingface/token`)

Without that, step 1 still runs and puts every word on one speaker — it prints a clear message and keeps going.

**B. MFA (step 2)** — a separate conda environment, because MFA pins old libraries:
```bash
conda create -n mfa2 -c conda-forge montreal-forced-aligner=3.1.0 "joblib=1.4.2" "setuptools<81"
conda activate mfa2
mfa model download acoustic english_us_arpa
mfa model download dictionary english_us_arpa
mfa model download g2p english_us_arpa        # lets MFA pronounce names/acronyms it doesn't know
```
⚠️ Use **3.1.0**. conda-forge ≥3.2 is currently broken (it pins a `kalpy` that lacks `G2PCompiler`).
MFA is CPU-only and happily runs on a cluster node; on the lab cluster there is already an `mfa2` env.

---

## Run it

Interactively — this is what an annotator should use. It asks for the recording (drag it into the window), where
the results go, and **how many people are talking**:
```bash
python run_all.py
```

Or say it all up front:
```bash
python run_all.py /path/to/audio.wav /path/to/out_dir --speakers 3
```

**`--speakers N` pins diarization to exactly N voices** (`min_speakers = max_speakers = N`); leave it off and it
guesses up to `--max-speakers` (default 5). A known headcount is by far the biggest quality win available here —
the guess is what splits one person across two labels. `--speakers 1` skips diarization entirely. `--no-ask`
suppresses all prompting for scripts and cluster jobs (it is implied when stdin is not a terminal).

If MFA lives elsewhere (e.g. the cluster), run steps 1–2 here, MFA there, step 4 here — `run_all.py` prints the
exact commands when it cannot find `mfa`:
```bash
python step1_whisper.py     audio.wav out/01_whisper
python step2_mfa_corpus.py  audio.wav out/01_whisper/audio.words.csv out/02_mfa_corpus
python step3_mfa_align.py   out/02_mfa_corpus out/03_mfa_out          # in the MFA env / on the cluster
python step4_textgrid.py    out/02_mfa_corpus/audio.sidecar.json out
```

### Output
| file | what |
|---|---|
| `<stem>_words.TextGrid` | one interval tier per speaker, one word per interval — **open this with the wav in Praat** |
| `<stem>_words.xlsx` | `onset \| offset \| Duration` in **ms** + one column per speaker + `timing_source` |
| `01_whisper/<stem>.words.csv` | Whisper's own words/speakers, before MFA |
| `02_mfa_corpus/` | what MFA was given (utterance windows + a sidecar mapping back to the original words) |

### After Praat: back to the lab spreadsheet
Clean `<stem>_words.TextGrid` in Praat (see `SOP_Convo_Praat_Cleaning.pdf`), then:
```bash
python textgrid_to_excel.py cleaned.TextGrid cleaned.xlsx --exclude
```
`onset | offset | Duration` in ms + one column per speaker; `--exclude` adds `exclude`/`exclude_reason` marking the
rows that are not words (`??`, `haha`). The same script converts the other way (`.xlsx` → `.TextGrid`) if you need
to open an existing word table in Praat. Round-trip is lossless (verified: 3,413 words, identical text, 0 ms drift).

**`timing_source`** is `mfa` for a properly aligned word, `whisper` for the few MFA merged or dropped (those
keep Whisper's late timing) — **check those first** when cleaning.

---

## Things that will bite you

- **MFA's exported TextGrids drop the first word of every utterance** (MFA 3.1.0 bug; it hit 11 of 12 files in
  one project). Step 4 therefore reads MFA's **database**, `~/Documents/MFA/<corpus>/<corpus>.db`, and finds it
  automatically. The exported TextGrids are a fallback only (`--mfa-out`).
- **MFA doesn't return your tokens one-for-one**: it splits hyphenated words and clitics (`u-shaped` → `u`+`shaped`).
  Step 4 matches words inside each utterance by gluing characters, so a split never shifts the labels after it.
- **Noisy room audio needs a wider search** or whole utterances silently fail to align. `align_config.yaml`
  (beam 100 / retry_beam 400) is passed automatically — MFA 3.1 has no `--beam` flag, it must come from a config file.
- **MFA runs one job per speaker** and crashes on a speaker with almost no words; step 2 drops those (listed in
  the sidecar as `dropped_speakers`).
- **Utterance windows are padded 0.5 s** on purpose, so MFA finds the first word's onset itself instead of
  inheriting Whisper's late one.
- **Run recordings one at a time** through MFA: concurrent runs share one database server and conflict.
- **Step 3 has two twins.** `step3_mfa_align.py` is the one to use — the Anaconda Prompt on Windows has no `bash`,
  so the `.sh` is a dead end there. `step3_mfa_align.sh` stays for the cluster; if you edit it on Windows keep it
  LF, because Linux bash rejects CRLF with `syntax error: unexpected end of file`.
- **Apple Silicon:** conda-forge may have no `osx-arm64` build of MFA 3.1.0. Build the env with
  `CONDA_SUBDIR=osx-64 conda create …` then `conda config --env --set subdir osx-64`; it runs under Rosetta.
  Whisper falls back to CPU (`compute_type=int8`) automatically — expect roughly real-time, not minutes.
- **Speaker labels are a guess.** Diarization splits one person across labels and merges two people more often
  than you would like; confirm them by ear before trusting them.

## Privacy

Patient recordings are PHI. Every stage here runs **locally or on lab hardware** — Whisper and MFA both run
offline, and nothing is sent to an API. Model weights are downloaded from HuggingFace the first time, which
sends no audio. Do not put recordings or transcripts in cloud storage.

## Validation

End-to-end test on a 2-minute conversation clip: 286 words, all placed, 264 aligned by MFA and 22 falling back
to Whisper timing. MFA put words a median **34 ms earlier** than Whisper on that clip; across full recordings
the gap measures ~65 ms. Word text and speaker assignment come through unchanged.

---
Built for the Hayden Lab convo pipeline. Companion documents: `SOP_Convo_Praat_Cleaning.md` (the human stage),
`audit_transcript.py` (automatic QC of a finished transcript).
