"""Additive governance-narrative layer over the existing, tested pipeline.

Nothing in this package replaces app/governance, app/synapse or
app/missions. It derives declared contracts, a display risk score, a
hash-chained ledger and a live red-team runner FROM the real decisions
those modules already make -- so the demo can narrate the system with
richer vocabulary without a single line of the tested execution path
changing.

See docs/AXON_BEASTMODE_AUDIT.md for exactly what was audited before this
package was written, and why several requested "new" subsystems are
wrappers rather than rewrites.
"""
