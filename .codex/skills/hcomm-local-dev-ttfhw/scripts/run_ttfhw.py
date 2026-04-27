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
    fields = parse_ccache_summary(text)
    patterns = {
        "cache_hit_direct": r"Direct:\s+(\d+)\s*/",
        "cache_hit_preprocessed": r"Preprocessed:\s+(\d+)\s*/",
        "cache_miss": r"Misses:\s+(\d+)\s*/",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            fields[key] = match.group(1)
    return fields


def parse_ccache_summary(text):
    match = re.search(r"^\s*Hits:\s+(\d+)\s*/\s*(\d+)\s*\(([0-9.]+)\s*%\)", text or "", re.MULTILINE)
    misses = re.search(r"^\s*Misses:\s+(\d+)\s*$", text or "", re.MULTILINE)
    return {
        "hits": int(match.group(1)) if match else None,
        "lookups": int(match.group(2)) if match else None,
        "hit_rate": f"{match.group(3)}%" if match else None,
        "misses": int(misses.group(1)) if misses else None,
    }


def ccache_delta(before, after):
    if before.get("hits") is None or after.get("hits") is None:
        return {"hits": None, "lookups": None, "hit_rate": None, "note": "ccache stats unavailable"}
    hits = after["hits"] - before["hits"]
    lookups = after["lookups"] - before["lookups"]
    if lookups <= 0:
        return {"hits": hits, "lookups": lookups, "hit_rate": None, "note": "no ccache lookups during incremental run"}
    return {"hits": hits, "lookups": lookups, "hit_rate": f"{hits / lookups * 100:.2f}%", "note": ""}


def display_ccache_dir(execution_mode, ccache_dir):
    if execution_mode == "docker":
        return str(CONTAINER_CCACHE)
    return "host-provided ccache directory"


def display_artifact_path(path, repo_root):
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return path.name


def add_incremental_ccache_stats(payload):
    ccache = payload["ccache"]
    after_first = parse_ccache_summary(ccache.get("after_first_run", ""))
    after_incremental = parse_ccache_summary(ccache.get("after_incremental_run", ""))
    delta = ccache_delta(after_first, after_incremental)
    ccache["after_first_run_summary"] = after_first
    ccache["after_incremental_run_summary"] = after_incremental
    ccache["incremental_run_delta"] = delta
    ccache["incremental_cumulative_hit_rate"] = after_incremental.get("hit_rate")
    ccache["incremental_delta_hit_rate"] = delta.get("hit_rate")


class Runner:
    def __init__(self, repo_root, execution_mode, ccache_dir, docker_image):
        self.repo_root = repo_root
        self.execution_mode = execution_mode
        self.ccache_dir = Path(ccache_dir).expanduser()
        self.docker_image = docker_image

    def run(self, name, command):
        started_at = now_iso()
        started = time.perf_counter()
        result = self._run(command)
        seconds = round(time.perf_counter() - started, 3)
        ended_at = now_iso()
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
    json_path = out_dir / f"{ts}.json"
    out_dir.mkdir(parents=True, exist_ok=True)

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
            "ccache_dir": display_ccache_dir(args.execution_mode, args.ccache_dir),
        },
        "git": git_info(repo_root),
        "steps": [],
        "ccache": {},
        "result": {
            "first_run_seconds": None,
            "incremental_run_seconds": None,
        },
        "artifacts": {
            "json": display_artifact_path(json_path, repo_root),
        },
    }

    started = time.perf_counter()
    runner = Runner(repo_root, args.execution_mode, args.ccache_dir, args.docker_image)
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
        add_incremental_ccache_stats(payload)
        payload["status"] = "success"
    except Exception as exc:
        payload["status"] = "failed"
        payload["error"] = str(exc)
    finally:
        if payload["result"]["incremental_run_seconds"] is None:
            payload["ccache"].setdefault("incremental_run_delta", {
                "hits": None,
                "lookups": None,
                "hit_rate": None,
                "note": "incremental run was not executed",
            })
            payload["ccache"].setdefault("incremental_cumulative_hit_rate", None)
            payload["ccache"].setdefault("incremental_delta_hit_rate", None)
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
    }, ensure_ascii=False))
    return 0 if payload["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
