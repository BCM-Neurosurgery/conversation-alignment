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

Hand-cleaning afterwards is still required: see `docs/SOP_Convo_Praat_Cleaning.pdf`.

---

## Install

One script builds both environments and downloads the aligner's English models:

```bat
setup_windows.bat          :: Windows, from Anaconda Prompt
```
```bash
bash setup_mac.sh          # macOS / Linux
```

It is just a wrapper around the two environment files, so you can do it by hand instead:

```bash
conda env create -f environment_whisper.yml      # transcription + the Excel converter
conda env create -f environment_mfa.yml          # the aligner
conda run -n mfa2 mfa model download acoustic   english_us_arpa
conda run -n mfa2 mfa model download dictionary english_us_arpa
conda run -n mfa2 mfa model download g2p        english_us_arpa
```

`python check_setup.py` verifies all of it and prints the exact command for anything missing.

**Two environments, not one**, because MFA pins old libraries that fight with whisperx. ⚠️ MFA must be **3.1.0** —
conda-forge ≥3.2 pins a `kalpy` without `G2PCompiler`. **ffmpeg is a real dependency** of whisperx (it shells out
to read audio) and pip does not provide the binary, so it is in `environment_whisper.yml`.

Diarization ("who spoke") additionally needs a free HuggingFace account:
1. accept the terms on **both** https://huggingface.co/pyannote/segmentation-3.0 and
   https://huggingface.co/pyannote/speaker-diarization-3.1
2. `huggingface-cli login` (or put the token in `~/.cache/huggingface/token`)

Without it every word lands on one speaker — `run_all.py` warns about this **before** the run starts rather than
letting you discover it afterwards.

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

**You do not switch environments.** `run_all.py` looks for `mfa` on PATH, and failing that for a conda env named
`mfa2` (or `mfa`), which it drives with `conda run -n mfa2 --no-capture-output`. Switching environments by hand
mid-pipeline was the single most confusing step for annotators.

If there is no MFA anywhere (e.g. it lives on the cluster), steps 1–2 still run and it prints the exact commands
to finish:
```bash
python step1_whisper.py     audio.wav out/01_whisper
python step2_mfa_corpus.py  audio.wav out/01_whisper/audio.words.csv out/02_mfa_corpus
python step3_mfa_align.py   out/02_mfa_corpus out/03_mfa_out          # in the MFA env / on the cluster
python step4_textgrid.py    out/02_mfa_corpus/audio.sidecar.json out   # back in the whisper env - needs pandas
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

## ⚠️ Open question: the g2p model may be costing us words (2026-09-27)

`--g2p_model_path` lets MFA invent a pronunciation for a word it does not know (names, "AFOs", "2002"). On the
one clip we have measured, **turning it OFF aligned strictly more words**:

| | MFA aligned | fell back to Whisper timing | words in the final TextGrid |
|---|---|---|---|
| g2p **on** (current default) | 280 | **22** | **277** |
| g2p **off** | 287 | **0** | **286** |

Same audio, same corpus, same MFA 3.1.0. With g2p on, 9 of 286 words are **missing from the TextGrid entirely**
and the fallback words land out of temporal order. The earlier "verified end-to-end" run shows the same 22
fallbacks, so this is long-standing behaviour, not a regression.

Plausible mechanism: a bad invented pronunciation makes MFA mis-segment or fail the utterance containing it, and
every word in it then keeps Whisper's ~65 ms-late timing.

**This is n=1** — a 2-minute single-speaker clip. Before changing the default, run both ways on a real recording:

```bash
python run_all.py <wav> <out_a> --speakers N
python run_all.py <wav> <out_b> --speakers N --no-g2p
```

and compare the `timing_source` column. If `--no-g2p` keeps winning, make it the default.

---

## Things that will bite you

- **A Praat tier cannot hold two words at once.** When a word's interval is entirely swallowed by the one
  before it, step 4 has to leave it out — this used to happen *silently*, so the `[done]` line claimed 276 words
  while the TextGrid held 263. Step 4 now names every dropped word and its timestamp, and prints both counts.
  The words are still in the `.xlsx`; they are missing only from the file the annotator opens. In practice these
  are always words that fell back to Whisper's timing, so this is downstream of the g2p problem above.
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
