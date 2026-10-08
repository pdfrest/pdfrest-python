# CIT quality tooling

This directory contains vendored contributor tooling, separate from project
source. It is maintained and tested in `cloud-innovation-team/cit-codex-skills`.
Executing the local copy requires no GitHub authentication or source-repository
access.

## Provenance

- Installed file: `.cit-quality/vendor/check_nfc_filenames.py`.
- Upstream file:
  `skills/cit-repository-quality-scaffolding/scripts/check_nfc_filenames.py`.
- Source revision: `2dbf02d13b73799d2fcf1d3c7bab0a8371fd82ee`.
- Source SHA-256:
  `83d3bb79ebf3a5d6cb4f213f3af4421bd258693057514637ce87f3fc00a79056`.
- Upstream suite:
  `skills/cit-repository-quality-scaffolding/scripts/test_scaffolding.py`.

The upstream behavioral suite tests rejection of non-NFC tracked filenames,
acceptance after a byte-preserving rename, and normalization collisions. It also
exercises the installed copy through the generated pre-commit hook. This
provenance identifies the source; rendering alone does not establish a passing
test run. Record the source revision and actual upstream validation in the PR.

## Upstream validation

On 2026-10-07, three focused upstream tests passed:

- `test_vendored_checker_is_separate_from_project_source` (includes the
  installed hook).
- `test_normalization_collision_is_reported_without_renaming`.
- `test_non_nfc_tracked_name_fails_hook_until_byte_preserving_rename`.

Command:
`uv run --script <skill>/scripts/test_scaffolding.py -v -n 2 -k "vendored_checker_is_separate or normalization_collision_is_reported or non_nfc_tracked_name_fails_hook_until_byte_preserving_rename" --durations=5`.

Result: `3 passed` on Python 3.13.11; rerun during this refresh. This is focused
validation, not a claim that the entire upstream suite or all checker failure
paths were exercised.

## Review and updates

Review source provenance, updates, and the repository's hook integration.
Implementation tests are maintained upstream; duplicate project tests are not
required for an unchanged, upstream-tested copy. Local behavior changes require
normal implementation review and appropriate regression coverage.

Update the checker and this provenance note together from the scaffolding skill.
Preserve the copied bytes; contribute fixes upstream instead of editing the
vendored copy. Keep this directory out of project source, test discovery,
coverage, and distribution inputs where those tools would otherwise traverse it.
The `linguist-vendored` attribute classifies the code; it does not disable
GitHub review requirements.

Run the installed hook from the repository root:

```shell
uvx --from pre-commit==4.6.2 pre-commit run check-nfc-filenames --all-files
```
