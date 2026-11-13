# Audit correction evidence

These are simulation results of the corrected RTL, separate from the historical
performance campaign. `manifest.json` records source and evidence hashes.

- Twelve valid runs compare all registers, DMEM and instruction counts with the
  Python model. CoreMark uses one iteration and checks the upstream CRCs.
- The two `bad_crc_*.xml` files intentionally contain failures: success of the
  rejection test requires the corrupted ELF to fail functional validation.
- The three `suite_*.xml` files contain 250 wrapper passes, including the
  documented expected machine-mode limitations.
- `historical_temporal_speedup.csv` is a separate recalculation of historical
  records, with incomplete provenance. It does not describe the corrected RTL.

No physical executions or new synthesis replicas are included. See
[the closure record](../../docs/cierre_auditoria_2026-11-09.md).
