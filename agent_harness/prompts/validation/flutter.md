---
name: flutter
match_files: pubspec.yaml
command_candidates: flutter analyze|dart analyze
blocking_severities: error
allow_nonzero_without_blockers: true
---
Flutter validation policy.

- Run the first available analysis command from the configured candidates.
- Treat analyzer `error` findings as blocking.
- Treat analyzer `warning` and `info` findings as advisory by default.
- If the analyzer exits non-zero but only reports advisory findings, keep the change reviewable and include the findings in feedback.
