#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
STEP 2 of 4 — words + speakers -> an MFA corpus.

MFA aligns TEXT to AUDIO inside utterance windows. This builds those windows from Whisper's words:
one interval tier per speaker, each interval = a run of that speaker's words, holding their text.

The window is PADDED by 0.5 s on each side on purpose. If a window started exactly at Whisper's first word
onset, MFA would inherit Whisper's (late) boundary instead of finding the word itself — which would defeat the
whole point of running MFA.

    python step2_mfa_corpus.py <audio.wav> <stem>.words.csv <corpus_dir>

Outputs:
    <corpus_dir>/<stem>.wav        (copy — MFA wants the audio beside the TextGrid)
    <corpus_dir>/<stem>.TextGrid   utterance windows, one tier per speaker
    <corpus_dir>/<stem>.sidecar.json  utterance -> the words it contains (step 4 maps MFA's output back with it)

Notes
- Speakers with fewer than MIN_WORDS words are dropped: MFA splits its jobs by speaker and crashes on a speaker
  with almost nothing in it. They are listed in the sidecar as `dropped_speakers`.
- Punctuation is stripped for MFA (it aligns pronunciations, not orthography). Step 4 puts the ORIGINAL
  punctuated word back into the final TextGrid, so nothing is lost.
"""
from __future__ import annotations
import argparse, json, re, shutil, sys
from pathlib import Path

GAP_S = 0.35          # a pause longer than this starts a new utterance
MAX_UTT_S = 15.0      # keep utterances short; MFA is happier and failures stay local
PAD_S = 0.5           # so MFA finds the first word's onset itself
MIN_WORDS = 10        # a speaker with fewer words than this crashes MFA's per-speaker job split


TAGS = {"??", "???", "[unclear]", "haha", "[laugh]"}   # annotation markers, not speech MFA can align


def norm(w: str) -> str:
    """MFA-facing token: lowercase, keep internal apostrophes, drop the rest.
    Returns '' for annotation tags (??, haha…) and anything with no letters — those are kept in the sidecar
    with their original times and re-inserted by step 4, never silently dropped."""
    if str(w).strip().lower() in TAGS:
        return ""
    w = re.sub(r"[^\w']+", " ", str(w).lower()).strip()
    return re.sub(r"\s+", " ", w)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("wav"); ap.add_argument("words_csv"); ap.add_argument("corpus_dir")
    a = ap.parse_args()
    import pandas as pd, soundfile as sf
    from praatio import textgrid as ptg

    stem = Path(a.wav).stem
    out = Path(a.corpus_dir); out.mkdir(parents=True, exist_ok=True)
    dur = sf.info(a.wav).duration
    W = pd.read_csv(a.words_csv, keep_default_na=False, na_values=[""])
    W = W[W.word.astype(str).str.strip() != ""].sort_values("start").reset_index(drop=True)

    counts = W.speaker.value_counts()
    keep = [s for s in counts.index if counts[s] >= MIN_WORDS]
    dropped = {s: int(counts[s]) for s in counts.index if s not in keep}
    if dropped:
        print(f"  [corpus] dropping tiny speakers (MFA crashes on them): {dropped}")

    tg = ptg.Textgrid()
    sidecar = {"wav": Path(a.wav).name, "stem": stem, "duration": dur, "dropped_speakers": dropped, "utterances": []}
    for spk in keep:
        g = W[W.speaker == spk].sort_values("start").reset_index(drop=True)
        utts, cur = [], []
        for i, r in g.iterrows():
            if cur and (r.start - g.end[cur[-1]] > GAP_S or r.end - g.start[cur[0]] > MAX_UTT_S):
                utts.append(cur); cur = []
            cur.append(i)
        if cur:
            utts.append(cur)

        ents, prev_end = [], 0.0
        for k, u in enumerate(utts):
            toks = [(int(g.index[i]), str(g.word[i]), norm(g.word[i]), float(g.start[i]), float(g.end[i])) for i in u]
            if not any(t[2] for t in toks):          # nothing pronounceable here — MFA would fail on it
                continue
            s = max(0.0, g.start[u[0]] - PAD_S)
            e = min(dur, g.end[u[-1]] + PAD_S)
            s = max(s, prev_end + 1e-4)                       # windows in one tier must not overlap
            if k + 1 < len(utts):                             # don't run into the next utterance
                e = min(e, (g.end[u[-1]] + g.start[utts[k + 1][0]]) / 2)
            if e - s < 0.05:
                continue
            ents.append((s, e, " ".join(t[2] for t in toks if t[2])))
            sidecar["utterances"].append({"speaker": str(spk), "start": round(s, 4), "end": round(e, 4),
                                          "words": [{"row": t[0], "original": t[1], "mfa": t[2],
                                                     "whisper_start": t[3], "whisper_end": t[4]} for t in toks]})
            prev_end = e
        if ents:
            tg.addTier(ptg.IntervalTier(str(spk), ents, 0, dur))
            print(f"  [corpus] {spk}: {len(ents)} utterances")

    tg.save(str(out / f"{stem}.TextGrid"), format="long_textgrid", includeBlankSpaces=True)
    if not (out / f"{stem}.wav").exists():
        shutil.copy2(a.wav, out / f"{stem}.wav")
    (out / f"{stem}.sidecar.json").write_text(json.dumps(sidecar, indent=1), encoding="utf-8")
    n = sum(len(u["words"]) for u in sidecar["utterances"])
    print(f"[done] {len(sidecar['utterances'])} utterances / {n} words -> {out}")


if __name__ == "__main__":
    main()
