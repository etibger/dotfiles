#!/usr/bin/env python3
"""Stream a VCD and emit a bounded counterexample evidence summary."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TextIO


@dataclass
class Signal:
    identifier: str
    width: int
    kind: str
    names: list[str] = field(default_factory=list)
    changes: int = 0
    first_time: int | None = None
    first_value: str | None = None
    last_time: int | None = None
    last_value: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vcd", type=Path)
    parser.add_argument(
        "--match",
        action="append",
        default=[],
        metavar="REGEX",
        help="retain bounded event samples for matching full signal names",
    )
    parser.add_argument("--max-events", type=int, default=40)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args()


def consume_block(first: str, handle: TextIO) -> str:
    parts = [first.strip()]
    while "$end" not in parts[-1]:
        line = handle.readline()
        if not line:
            break
        parts.append(line.strip())
    return " ".join(parts)


def parse_header(handle: TextIO) -> tuple[dict[str, Signal], str, int, set[str]]:
    signals: dict[str, Signal] = {}
    scope: list[str] = []
    scopes: set[str] = set()
    timescale = "unspecified"

    while True:
        line = handle.readline()
        if not line:
            raise ValueError("VCD ended before $enddefinitions")
        stripped = line.strip()
        if stripped.startswith("$scope"):
            fields = stripped.split()
            if len(fields) >= 3:
                scope.append(fields[2])
                scopes.add(".".join(scope))
        elif stripped.startswith("$upscope"):
            if scope:
                scope.pop()
        elif stripped.startswith("$timescale"):
            block = consume_block(stripped, handle)
            timescale = block.replace("$timescale", "").replace("$end", "").strip()
        elif stripped.startswith("$var"):
            block = consume_block(stripped, handle)
            fields = block.split()
            if len(fields) < 6:
                continue
            kind, width_text, identifier = fields[1:4]
            try:
                width = int(width_text)
            except ValueError:
                width = 0
            reference = " ".join(fields[4:-1])
            full_name = ".".join([*scope, reference]) if scope else reference
            signal = signals.setdefault(identifier, Signal(identifier, width, kind))
            if full_name not in signal.names:
                signal.names.append(full_name)
        elif stripped.startswith("$enddefinitions"):
            consume_block(stripped, handle)
            return signals, timescale, handle.tell(), scopes


def decode_change(line: str) -> tuple[str, str] | None:
    if not line:
        return None
    if line[0] in "01xXzZ":
        return line[1:].strip(), line[0].lower()
    if line[0] in "bBrRsS":
        fields = line.split(maxsplit=1)
        if len(fields) == 2:
            return fields[1].strip(), fields[0][1:]
    return None


def analyze(
    handle: TextIO,
    signals: dict[str, Signal],
    patterns: list[re.Pattern[str]],
    max_events: int,
) -> tuple[int, list[dict[str, object]], set[str]]:
    selected = {
        identifier
        for identifier, signal in signals.items()
        if patterns and any(p.search(name) for p in patterns for name in signal.names)
    }
    events: list[dict[str, object]] = []
    current_time = 0
    last_time = 0

    for raw_line in handle:
        line = raw_line.strip()
        if not line or line.startswith("$"):
            continue
        if line.startswith("#"):
            try:
                current_time = int(line[1:])
                last_time = max(last_time, current_time)
            except ValueError:
                pass
            continue
        decoded = decode_change(line)
        if decoded is None:
            continue
        identifier, value = decoded
        signal = signals.get(identifier)
        if signal is None:
            continue
        signal.changes += 1
        if signal.first_time is None:
            signal.first_time = current_time
            signal.first_value = value
        signal.last_time = current_time
        signal.last_value = value
        if identifier in selected and len(events) < max_events:
            events.append(
                {"time": current_time, "signal": signal.names[0], "value": value}
            )
    return last_time, events, selected


def signal_record(signal: Signal) -> dict[str, object]:
    return {
        "names": signal.names,
        "width": signal.width,
        "kind": signal.kind,
        "changes": signal.changes,
        "first": {"time": signal.first_time, "value": signal.first_value},
        "last": {"time": signal.last_time, "value": signal.last_value},
    }


def main() -> int:
    args = parse_args()
    if args.max_events < 0 or args.top < 1:
        print("--max-events must be nonnegative and --top must be positive", file=sys.stderr)
        return 2
    try:
        patterns = [re.compile(value) for value in args.match]
    except re.error as exc:
        print(f"invalid --match regex: {exc}", file=sys.stderr)
        return 2
    if not args.vcd.is_file() or args.vcd.stat().st_size == 0:
        print(f"missing or empty VCD: {args.vcd}", file=sys.stderr)
        return 1

    try:
        with args.vcd.open("r", encoding="utf-8", errors="replace") as handle:
            signals, timescale, data_offset, scopes = parse_header(handle)
            handle.seek(data_offset)
            last_time, events, selected = analyze(
                handle, signals, patterns, args.max_events
            )
    except (OSError, ValueError) as exc:
        print(f"failed to parse VCD: {exc}", file=sys.stderr)
        return 1

    active = sorted(
        (signal for signal in signals.values() if signal.changes),
        key=lambda signal: (-signal.changes, signal.names[0]),
    )
    chosen = sorted(
        (signals[identifier] for identifier in selected),
        key=lambda signal: signal.names[0],
    )
    result = {
        "file": str(args.vcd.resolve()),
        "bytes": os.path.getsize(args.vcd),
        "timescale": timescale,
        "scope_count": len(scopes),
        "identifier_count": len(signals),
        "active_identifier_count": len(active),
        "waveform_end": last_time,
        "waveform_end_interpretation": (
            "End of exported CEX; often the violation boundary, not an independently decoded failure time."
        ),
        "match_patterns": args.match,
        "matched": [signal_record(signal) for signal in chosen],
        "sampled_events": events,
        "most_active": [signal_record(signal) for signal in active[: args.top]],
    }

    if args.as_json:
        json.dump(result, sys.stdout, indent=2)
        print()
    else:
        print(f"VCD: {result['file']}")
        print(f"Size: {result['bytes']} bytes")
        print(f"Timescale: {timescale}")
        print(
            f"Scopes: {len(scopes)}; identifiers: {len(signals)}; "
            f"active: {len(active)}"
        )
        print(f"Waveform end: {last_time} ({timescale})")
        print(result["waveform_end_interpretation"])
        if args.match:
            print(f"Matched identifiers: {len(chosen)}")
            for signal in chosen:
                name = signal.names[0]
                print(
                    f"  {name}: changes={signal.changes} "
                    f"first={signal.first_time}:{signal.first_value} "
                    f"last={signal.last_time}:{signal.last_value}"
                )
        print("Most active identifiers:")
        for signal in active[: args.top]:
            print(f"  {signal.names[0]}: {signal.changes} changes")
        if events:
            print("Sampled matching events:")
            for event in events:
                print(f"  #{event['time']} {event['signal']}={event['value']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
