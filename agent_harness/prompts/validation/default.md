---
name: default
match_files:
command_candidates:
blocking_severities: error
allow_nonzero_without_blockers: false
---
Default validation policy.

- If no validation command is configured, validation is skipped.
- Non-blocking findings can be mentioned in review feedback, but only configured blocking severities should reject a change.
- Prefer concrete validator output over assumptions.
