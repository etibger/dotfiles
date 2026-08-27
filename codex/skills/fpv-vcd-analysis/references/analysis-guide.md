# FPV counterexample VCD analysis guide

## Establish identity first

Record the candidate SHA, FTRun target, failed property, VCD type (raw FTS or
QuietTrace), and file size. Prefer the QuietTrace VCD for a focused cone and the
raw VCD as a reliable fallback. If the property named in the report is not
represented by the expected design signals, inspect the raw VCD or restore the
JDB.

## Select signals from the property

Start with clock/reset, then the property antecedent, consequent, enables,
valid/ready handshakes, relevant state, and one layer of data/control inputs.
Use anchored or specific regexes on large traces. Avoid interpreting every
toggling signal as causal.

For each important signal, record its value before and at the final relevant
cycle. For temporal properties, explicitly map cycles to delay/range operators
in the SVA rather than relying on a visual impression.

## Evidence language

- Direct: the VCD declares a signal and shows a value transition at a timestamp.
- Correlated: a report identifies the failed property and the trace contains
  its relevant signals.
- Inferred: the final exported timestamp is treated as the violation boundary,
  or a signal transition is proposed as causal.

Label inferences. A VCD generally does not encode an authoritative failure
timestamp or causal cone metadata.

## Restore when needed

Use `$jaspergold-local-fpv` restore guidance when the VCD omits internal state,
the property is optimized/renamed, X handling matters, or causality is unclear.
Prefer `jg_prop_timeline`, `jg_val_in_window`, `jg_why`, and `jg_fanin` before
exporting another large waveform.
