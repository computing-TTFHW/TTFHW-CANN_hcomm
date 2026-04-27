#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


DOCKER_IMAGE = "swr.cn-north-4.myhuaweicloud.com/ci_cann/ubuntu24.04_x86:lv6_v1.1031"
CONTAINER_WORKSPACE = Path("/workspace/hcomm")
CONTAINER_CCACHE = Path("/home/jenkins/.cache/ccache")

METRICS = {
    "first_build_success": "time bash build.sh --noclean",
    "first_ut_success": "time bash build.sh --ut --noclean",
}


def now_iso():
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def timestamp_slug():
    return dt.datetime.now(dt.timezone.utc).astimezone().strftime("%Y%m%dT%H%M%S%z")


def find_repo_root(start):
    for candidate in [start, *start.parents]:
        if (candidate / "build.sh").is_file() and (candidate / ".git").exists():
            return candidate
    raise RuntimeError(f"Could not find hcomm repository root from {start}")


def run_capture(cmd, cwd, check=False):
    result = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True)
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
    return result


def git_info(repo_root):
    branch = run_capture(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo_root).stdout.strip()
    commit = run_capture(["git", "rev-parse", "HEAD"], repo_root).stdout.strip()
    status = run_capture(["git", "status", "--porcelain"], repo_root).stdout
    return {
        "branch": branch,
        "commit": commit,
        "dirty": bool(status.strip()),
    }


def parse_ccache_stats(text):
    fields = {}
    patterns = {
        "cache_hit_direct": r"Direct:\s+(\d+)\s*/",
        "cache_hit_preprocessed": r"Preprocessed:\s+(\d+)\s*/",
        "cache_miss": r"Misses:\s+(\d+)\s*/",
        "hit_rate": r"Hit rate:\s+([0-9.]+ ?%)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            fields[key] = match.group(1)
    return fields


def append_log(log_path, title, command, result):
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"\n===== {title} =====\n")
        handle.write(f"$ {command}\n")
        handle.write(f"[returncode={result.returncode}]\n")
        handle.write(result.stdout)
        handle.write(result.stderr)
        if not result.stderr.endswith("\n"):
            handle.write("\n")


class Runner:
    def __init__(self, repo_root, execution_mode, ccache_dir, docker_image, log_path):
        self.repo_root = repo_root
        self.execution_mode = execution_mode
        self.ccache_dir = Path(ccache_dir).expanduser()
        self.docker_image = docker_image
        self.log_path = log_path

    def run(self, name, command):
        started_at = now_iso()
        started = time.perf_counter()
        result = self._run(command)
        seconds = round(time.perf_counter() - started, 3)
        ended_at = now_iso()
        append_log(self.log_path, name, command, result)
        return {
            "name": name,
            "command": command,
            "status": "success" if result.returncode == 0 else "failed",
            "returncode": result.returncode,
            "started_at": started_at,
            "ended_at": ended_at,
            "seconds": seconds,
        }, result

    def _run(self, command):
        shell = self._shell(command)
        if self.execution_mode == "host":
            return subprocess.run(["bash", "-lc", shell], cwd=str(self.repo_root), text=True, capture_output=True)

        self.ccache_dir.mkdir(parents=True, exist_ok=True)
        docker_cmd = [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "bash",
            "-v",
            f"{self.repo_root}:{CONTAINER_WORKSPACE}",
            "-v",
            f"{self.ccache_dir}:{CONTAINER_CCACHE}",
            "-w",
            str(CONTAINER_WORKSPACE),
            self.docker_image,
            "-lc",
            shell,
        ]
        return subprocess.run(docker_cmd, text=True, capture_output=True)

    @staticmethod
    def _shell(command):
        return "\n".join(
            [
                "set -o pipefail",
                "if [ -n \"${ASCEND_CANN_PACKAGE_PATH:-}\" ] && [ -f \"${ASCEND_CANN_PACKAGE_PATH}/set_env.sh\" ]; then source \"${ASCEND_CANN_PACKAGE_PATH}/set_env.sh\"; fi",
                "if [ -n \"${ASCEND_HOME_PATH:-}\" ] && [ -f \"${ASCEND_HOME_PATH}/set_env.sh\" ]; then source \"${ASCEND_HOME_PATH}/set_env.sh\"; fi",
                "if [ -f \"/usr/local/Ascend/ascend-toolkit/latest/set_env.sh\" ]; then source \"/usr/local/Ascend/ascend-toolkit/latest/set_env.sh\"; fi",
                command,
            ]
        )


def run_metric(args):
    repo_root = find_repo_root(Path(__file__).resolve())
    metric = args.metric
    command = METRICS[metric]
    ts = timestamp_slug()
    out_dir = repo_root / "output" / "ttfhw" / metric
    log_dir = repo_root / "output" / "ttfhw" / "logs"
    json_path = out_dir / f"{ts}.json"
    log_path = log_dir / f"{metric}_{ts}.log"
    out_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema_version": "2.0",
        "skill": "hcomm-local-dev-ttfhw",
        "repo": "hcomm",
        "metric": metric,
        "command": command,
        "status": "running",
        "started_at": now_iso(),
        "ended_at": None,
        "execution_mode": args.execution_mode,
        "environment": {
            "docker_image": args.docker_image if args.execution_mode == "docker" else "",
            "ccache_dir": str(Path(args.ccache_dir).expanduser()),
        },
        "git": git_info(repo_root),
        "steps": [],
        "ccache": {},
        "result": {
            "first_run_seconds": None,
            "incremental_run_seconds": None,
        },
        "artifacts": {
            "json": str(json_path),
            "stdout_log": str(log_path),
        },
    }

    started = time.perf_counter()
    runner = Runner(repo_root, args.execution_mode, args.ccache_dir, args.docker_image, log_path)
    try:
        if args.execution_mode == "docker" and shutil.which("docker") is None:
            raise RuntimeError("docker not found in PATH")

        step, _ = runner.run("ccache_zero", "ccache -z")
        payload["steps"].append(step)
        if step["status"] != "success":
            raise RuntimeError("ccache -z failed")

        step, result = runner.run("ccache_before", "ccache -s")
        payload["steps"].append(step)
        payload["ccache"]["before"] = result.stdout + result.stderr

        step, _ = runner.run("first_run", command)
        payload["steps"].append(step)
        payload["result"]["first_run_seconds"] = step["seconds"]
        if step["status"] != "success":
            raise RuntimeError("first run failed")

        step, result = runner.run("ccache_after_first_run", "ccache -s")
        payload["steps"].append(step)
        payload["ccache"]["after_first_run"] = result.stdout + result.stderr

        step, _ = runner.run("incremental_run", command)
        payload["steps"].append(step)
        payload["result"]["incremental_run_seconds"] = step["seconds"]
        if step["status"] != "success":
            raise RuntimeError("incremental run failed")

        step, result = runner.run("ccache_after_incremental_run", "ccache -s")
        payload["steps"].append(step)
        payload["ccache"]["after_incremental_run"] = result.stdout + result.stderr
        payload["ccache"].update(parse_ccache_stats(payload["ccache"]["after_incremental_run"]))
        payload["status"] = "success"
    except Exception as exc:
        payload["status"] = "failed"
        payload["error"] = str(exc)
    finally:
        payload["ended_at"] = now_iso()
        payload["total_seconds"] = round(time.perf_counter() - started, 3)
        json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return payload


def main():
    parser = argparse.ArgumentParser(description="Measure hcomm TTFHW using the two fixed project commands.")
    parser.add_argument("--metric", required=True, choices=sorted(METRICS))
    parser.add_argument("--execution-mode", default="docker", choices=["docker", "host"])
    parser.add_argument("--docker-image", default=DOCKER_IMAGE)
    parser.add_argument("--ccache-dir", default=str(Path.home() / ".cache" / "hcomm-ttfhw-ccache"))
    args = parser.parse_args()

    payload = run_metric(args)
    print(json.dumps({
        "status": payload["status"],
        "metric": payload["metric"],
        "command": payload["command"],
        "first_run_seconds": payload["result"]["first_run_seconds"],
        "incremental_run_seconds": payload["result"]["incremental_run_seconds"],
        "json": payload["artifacts"]["json"],
        "log": payload["artifacts"]["stdout_log"],
    }, ensure_ascii=False))
    return 0 if payload["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
