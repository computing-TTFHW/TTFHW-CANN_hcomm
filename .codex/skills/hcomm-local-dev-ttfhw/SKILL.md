---
name: hcomm-local-dev-ttfhw
description: "Measure TTFHW for the current hcomm repository only. Use exactly two metrics: `first_build_success` with `time bash build.sh --noclean`, and `first_ut_success` with `time bash build.sh --ut --noclean`; each metric records first-run duration and second-run incremental duration under `output/ttfhw/`."
---

# HCOMM Local Dev TTFHW

This skill is only for the current `hcomm` repository.

## Metrics

TTFHW has two metrics:

1. `first_build_success`
2. `first_ut_success`

The core commands are fixed:

```bash
time bash build.sh --noclean
time bash build.sh --ut --noclean
```

For each metric, run the command twice in the same workspace:

1. first run: record `first_run_seconds`
2. second run: record `incremental_run_seconds`

## Ground Rules

- Run from the repository root.
- Prefer Docker image `swr.cn-north-4.myhuaweicloud.com/ci_cann/ubuntu24.04_x86:lv6_v1.1031`.
- Mount a persistent ccache directory to `/home/jenkins/.cache/ccache` when running in Docker.
- Run `ccache -z` before the first run.
- Run `ccache -s` before the first run, after the first run, and after the second run.
- Always write JSON and log files under `output/ttfhw/`, even on failure.
- Do not add extra TTFHW scenarios unless the user explicitly changes the metric definition.

## Script

Use:

```bash
python3 .codex/skills/hcomm-local-dev-ttfhw/scripts/run_ttfhw.py --metric first_build_success
python3 .codex/skills/hcomm-local-dev-ttfhw/scripts/run_ttfhw.py --metric first_ut_success
```

The script records:

- exact command
- first-run duration
- second-run incremental duration
- ccache stats
- git branch, commit, and dirty state
- JSON and combined stdout/stderr log paths

## Output

The script writes results under:

```text
output/ttfhw/first_build_success/
output/ttfhw/first_ut_success/
output/ttfhw/logs/
```

## Guardrails

- Do not use this skill outside `hcomm`.
- Do not delete user changes.
- Do not silently substitute `--pkg`, `--st`, coverage, or custom commands for the two fixed TTFHW commands.
