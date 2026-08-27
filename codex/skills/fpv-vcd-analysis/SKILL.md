---
name: fpv-vcd-analysis
description: Inspect JasperGold counterexample VCDs locally and produce a bounded evidence summary of scopes, signals, transitions, and the trace endpoint. Use after an FPV failure artifact is copied locally; do not infer RTL root cause from waveform shape alone.
---

# FPV VCD Analysis

Analyze the retained VCD together with the property name, proof report, and run
log. A VCD is evidence for a counterexample trajectory; it does not by itself
identify the violated specification or prove that a candidate fix is correct.

## Procedure

1. Verify the VCD is nonempty and came from the intended candidate/run.
2. Find the failed property in `proof_report.rpt`, result JSON, or `run.log`.
3. Run [scripts/analyze_vcd.py](scripts/analyze_vcd.py) with signal-name regexes
   derived from that property and its cone:

   ```sh
   python3 ~/.config/codex/skills/fpv-vcd-analysis/scripts/analyze_vcd.py \
     counterexample.vcd --match 'clk|reset' --match 'valid|ready'
   ```

4. Correlate the reported waveform endpoint and transitions with the property
   antecedent/consequent. Treat the last timestamp as the end of the exported
   CEX, often the violation boundary, not an independently decoded failure time.
5. State what is directly observed, what is inferred, and what still requires a
   restored Jasper cone/why query.

Read [references/analysis-guide.md](references/analysis-guide.md) for signal
selection, evidence standards, and escalation to a saved JDB.

The analyzer streams value changes and keeps bounded event samples, so it can
summarize large VCDs without loading the whole waveform into memory.
