#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Convert between the two formats the lab uses, in either direction. Run it on your finished Praat file.

    python textgrid_to_excel.py  my_file.TextGrid  my_file.xlsx      # after cleaning in Praat  ← the usual one
    python textgrid_to_excel.py  my_file.xlsx      my_file.TextGrid  # to open a word table in Praat

The Excel layout is the lab's: `onset | offset | Duration` in MILLISECONDS, then one column per speaker, one word
per row, with the word sitting in its speaker's column.

Options
    --exclude     add `exclude` / `exclude_reason` columns marking the rows that are not words (?? and haha),
                  so an analysis can drop them with one filter
    --round N     decimal places for the millisecond columns (default 2, which matches the existing files)
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path

TAGS_UNCLEAR = {"??", "???", "[unclear]", "x", "xx", "xxx", "xxxx", "inaudible", "unintelligible", "unclear"}
TAGS_LAUGH = {"haha", "[laugh]", "laugh", "laughs", "laughter", "laughing"}


def bare(w: str) -> str:
    """lowercase, stripped of surrounding punctuation — old files contain 'xxx,' and 'X.' as well as 'xxx'."""
    return str(w).strip().strip(" .,!?;:\"'()-").lower()


def is_laughter(w: str) -> bool:
    """'haha', 'hehehe', 'Hahaha' … — only h/a/e letters with at least two h's (so the word 'he' is safe)."""
    t = "".join(c for c in w.lower() if c.isalpha())
    return bare(w) in TAGS_LAUGH or (len(t) >= 3 and set(t) <= set("hae") and t.count("h") >= 2)


def tg_to_xlsx(src, dst, ndp, add_exclude):
    import pandas as pd
    from praatio import textgrid as ptg
    tg = ptg.openTextgrid(str(src), includeEmptyIntervals=False, duplicateNamesMode="rename")
    speakers = [n for n in tg.tierNames
                if getattr(tg.getTier(n), "tierType", "") == "IntervalTier" and "phone" not in n.lower()]
    rows = []
    for spk in speakers:
        for e in tg.getTier(spk).entries:
            if e.label.strip():
                rows.append((round(e.start * 1000, ndp), round(e.end * 1000, ndp), spk, e.label.strip()))
    rows.sort()
    out = []
    for on, off, spk, word in rows:
        r = {"onset": on, "offset": off, "Duration": round(off - on, ndp)}
        r.update({s: (word if s == spk else "") for s in speakers})
        if add_exclude:
            kind = "unintelligible" if bare(word) in TAGS_UNCLEAR else "laughter" if is_laughter(word) else ""
            r["exclude"], r["exclude_reason"] = (1 if kind else 0), kind
        out.append(r)
    cols = ["onset", "offset", "Duration"] + speakers + (["exclude", "exclude_reason"] if add_exclude else [])
    pd.DataFrame(out, columns=cols).to_excel(dst, index=False)
    print(f"[done] {len(out)} words, speakers {speakers} -> {dst}")


def xlsx_to_tg(src, dst):
    import pandas as pd
    from praatio import textgrid as ptg
    df = pd.read_excel(src, sheet_name=0, keep_default_na=False, na_values=[""])
    low = {str(c).strip().lower(): c for c in df.columns}
    oc, fc = low["onset"], low["offset"]
    skip = {oc, fc, low.get("duration"), low.get("exclude"), low.get("exclude_reason"), low.get("note")}
    speakers = [c for c in df.columns if c not in skip
                and df[c].map(lambda v: isinstance(v, str) and v.strip() != "").any()]
    dur = float(df[fc].max()) / 1000 + 0.5
    tg = ptg.Textgrid()
    for spk in speakers:
        ents, last = [], 0.0
        idx = [i for i in range(len(df)) if isinstance(df[spk].iat[i], str) and df[spk].iat[i].strip()]
        for i in sorted(idx, key=lambda k: float(df[oc].iat[k])):
            s, e = max(float(df[oc].iat[i]) / 1000, last), float(df[fc].iat[i]) / 1000
            if e - s > 1e-6:
                ents.append((s, e, str(df[spk].iat[i]).strip())); last = e
        tg.addTier(ptg.IntervalTier(str(spk), ents, 0, dur))
    tg.save(str(dst), format="long_textgrid", includeBlankSpaces=True)
    print(f"[done] {sum(len(tg.getTier(s).entries) for s in tg.tierNames)} words, tiers {list(tg.tierNames)} -> {dst}")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src"); ap.add_argument("dst")
    ap.add_argument("--exclude", action="store_true"); ap.add_argument("--round", type=int, default=2)
    a = ap.parse_args()
    src, dst = Path(a.src), Path(a.dst)
    if not src.exists():
        raise SystemExit(f"no such file: {src}")
    if src.suffix.lower() == ".textgrid":
        tg_to_xlsx(src, dst, a.round, a.exclude)
    elif src.suffix.lower() in (".xlsx", ".xlsm"):
        xlsx_to_tg(src, dst)
    else:
        raise SystemExit("give me a .TextGrid or an .xlsx")


if __name__ == "__main__":
    main()
