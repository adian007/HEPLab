"""Certified luminosity intervals with frozen content identity."""

from __future__ import annotations

import json
from bisect import bisect_right
from pathlib import Path

from .provenance import file_hash


class LumiMask:
    def __init__(self, path: str | Path):
        self.sha256 = file_hash(path)
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("certification must map run numbers to lumi intervals")
        self.intervals = {}
        self.starts = {}
        for run, intervals in raw.items():
            if not run.isdigit() or not isinstance(intervals, list):
                raise ValueError("invalid certification run/intervals")
            ordered = sorted(intervals)
            end = -1
            for pair in ordered:
                if (
                    not isinstance(pair, list)
                    or len(pair) != 2
                    or any(type(x) is not int for x in pair)
                    or not 0 < pair[0] <= pair[1]
                    or pair[0] <= end
                ):
                    raise ValueError("invalid or overlapping certification interval")
                end = pair[1]
            self.intervals[int(run)] = ordered
            self.starts[int(run)] = [pair[0] for pair in ordered]

    def accepts(self, run: int, lumi: int) -> bool:
        starts = self.starts.get(run, [])
        index = bisect_right(starts, lumi) - 1
        return index >= 0 and lumi <= self.intervals[run][index][1]
