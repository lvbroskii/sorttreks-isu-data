# Public regression fixtures

These fixtures and the deterministic builders in `src/isu_pilot/synthetic.py`
are **synthetic, not official ISU captures**. They exercise the actual adapters,
matching, authority, persistence and workflow contracts. They do not verify live
Montreal availability or the ISU service's real pre-race status vocabulary.

Historical HTML, PDF extracts, raw API captures, compressed archives and their
actual-source tests remain local only. Public CI neither loads nor publishes them.
The live collector uses only HTTP source evidence, never these builders.
