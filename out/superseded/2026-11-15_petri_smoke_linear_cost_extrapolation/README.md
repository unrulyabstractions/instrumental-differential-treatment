# Superseded: Petri smoke cost summary with a linear projection

This summary projected a 30-turn transcript by fitting a line through per-call dollars. The first auditor call writes the whole system prompt to the cache, so the fitted line falls and the projection came out negative. The current summary in out/main/petri_20261115/smoke/ projects tokens by prompt growth per call. The measured costs per call are the same in both files.
