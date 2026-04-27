# TTFHW-CANN_hcomm

This repository stores the TTFHW measurement skill, raw JSON artifacts, and HTML visualizations for the CANN `hcomm` project.

GitHub Pages site:

https://computing-ttfhw.github.io/TTFHW-CANN_hcomm/

## Purpose

The repository is an evidence bundle for local developer experience measurements on `hcomm`. It keeps the measurement workflow and the produced results together so the numbers can be reviewed, reproduced, and compared over time.

The current TTFHW definition uses two fixed metrics:

| Metric | Command | Meaning |
| --- | --- | --- |
| `first_build_success` | `time bash build.sh --noclean` | Time to the first successful local build, plus the second incremental build time. |
| `first_ut_success` | `time bash build.sh --ut --noclean` | Time to the first successful UT run, plus the second incremental UT time when the first run succeeds. |

## View Results

Open the GitHub Pages entry point:

https://computing-ttfhw.github.io/TTFHW-CANN_hcomm/

Direct report links:

- `first_build_success`: https://computing-ttfhw.github.io/TTFHW-CANN_hcomm/output/ttfhw/visualizations/first_build_success_20260425T162750+0800.html
- `first_ut_success`: https://computing-ttfhw.github.io/TTFHW-CANN_hcomm/output/ttfhw/visualizations/first_ut_success_20260425T164601+0800.html

## Current Results

| Metric | Status | First run | Second incremental run | Notes |
| --- | --- | ---: | ---: | --- |
| `first_build_success` | Success | `1038.111s` | `4.728s` | Incremental build completed successfully. |
| `first_ut_success` | Failed | `58678.951s` | `-` | First UT build failed, so the second incremental run was not executed. The raw log files are not stored in this repository. |

## Measurement Environment

| Item | Value |
| --- | --- |
| Execution mode | Docker |
| Docker image | `swr.cn-north-4.myhuaweicloud.com/ci_cann/ubuntu24.04_x86:lv6_v1.1031` |
| Docker version | `29.2.1` |
| Host CPU | `13th Gen Intel(R) Core(TM) i7-13700` |
| Host CPU count | `24` |
| Host memory | `15 GiB RAM, 4 GiB swap` |
| NPU | Not required for these TTFHW measurements. |

## Repository Layout

```text
index.html
  GitHub Pages entry page.

.codex/skills/hcomm-local-dev-ttfhw/
  Codex skill definition and scripts used to measure and render hcomm TTFHW results.

output/ttfhw/first_build_success/
  Raw JSON result for the build metric.

output/ttfhw/first_ut_success/
  Raw JSON result for the UT metric.

output/ttfhw/visualizations/
  Standalone HTML reports generated from the JSON files.
```

## Reproduce

Run from an `hcomm` checkout with the required CANN build environment. Docker validation uses:

```text
swr.cn-north-4.myhuaweicloud.com/ci_cann/ubuntu24.04_x86:lv6_v1.1031
```

Example commands:

```bash
python3 .codex/skills/hcomm-local-dev-ttfhw/scripts/run_ttfhw.py --metric first_build_success
python3 .codex/skills/hcomm-local-dev-ttfhw/scripts/run_ttfhw.py --metric first_ut_success
```

The script records `ccache` stats before and after the runs. The `--noclean` option is required for meaningful incremental timing and cache reuse in this project.
