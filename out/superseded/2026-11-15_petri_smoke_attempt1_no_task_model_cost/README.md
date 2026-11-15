# Superseded: Petri smoke, first attempt

The first smoke run stopped before any model call: Inspect's cost_limit asked for a price for the task's placeholder model (none/none). No tokens were spent. The fix registers a zero price for it in script/petri/petri_smoke_audit.py.
