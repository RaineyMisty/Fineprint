# Synthetic benchmark protocol

All policy, claim, provider, price and patient data are fictional. Gold rules and
claim expectations are authored independently of engine output. Original curated
policy JSON supplies the gold for Aurora and Mosaic. The prose now explicitly
lists Aurora's out-of-network service codes, Mosaic's in-network cosmetic exclusion,
and the therapy endorsement's zero coinsurance, eliminating undocumented defaults.

The fallback compiler and its development tests are committed **before** creating
new held-out insurers. Freeze `fineprint/compiler.py` and record its SHA-256 below
when authoring the held-out set. Do not change the parser in response to those
results; report failures. The author knows the grammar, so this is an author-created
format holdout, not a blinded external benchmark or evidence of real-world accuracy.
No insurer-specific dispatch or gold lookups are permitted in the compiler.

Evaluate all original documents and both new insurer formats. Never drop failed
compilations from denominators. Report seen, held-out and pooled counts. Repeated
claims share a policy; extraction must be scored once per policy, not once per claim.
LLM provider evaluations require real credentials and must name the selected backend;
transport stubs belong exclusively to unit tests. Default evaluation is offline.
