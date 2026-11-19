"""The worker (T-502): jobs from the Postgres queue (ADR-009), runs of the agent graph with their
checkpoints in Postgres (schema lg), so a run goes on after a restart from its last step."""
