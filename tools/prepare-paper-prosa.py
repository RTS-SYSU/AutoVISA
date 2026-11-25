"""Build Prosa 0.6 modules required by the POET paper certificate."""

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import os
from pathlib import Path
import subprocess
import tempfile


MODULES = (
    "implementation/refinements/FP/fast_search_space",
    "implementation/refinements/FP/refinements",
    "implementation/facts/job_constructor",
    "results/rta/ideal/fp/fully_preemptive",
    "implementation/refinements/FP/preemptive_sched",
)
REVISION = "414e66760333eaa4ef78c685bcf53291c527a548"


def dependency_graph(root, rocq, env):
    sources = subprocess.check_output(
        ["git", "ls-files", "--", "*.v"], cwd=root, encoding="utf-8"
    ).splitlines()
    # The Windows device name aux.v is outside this certificate's dependency closure.
    if os.name == "nt":
        sources = [file for file in sources if Path(file).stem.lower() != "aux"]
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", prefix="autovisa-coqdep-", dir=root, delete=False
    ) as stream:
        stream.write("\n".join(sources) + "\n")
        project = Path(stream.name)
    try:
        result = subprocess.run(
            [str(rocq), "dep", "-R", ".", "prosa", "-f", project.name],
            cwd=root, env=env, capture_output=True, encoding="utf-8", errors="replace"
        )
        if result.returncode:
            raise RuntimeError(result.stderr or result.stdout)
    finally:
        project.unlink()
    graph = {}
    for line in result.stdout.splitlines():
        targets, _, dependencies = line.partition(":")
        files = [path.replace("\\", "/").removeprefix("./") for path in dependencies.split()]
        for target in targets.split():
            target = target.replace("\\", "/").removeprefix("./")
            if target.endswith(".vo"):
                graph[target] = {dep for dep in files if dep.endswith(".vo")}
    return graph


def build(root, rocq, jobs):
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if revision != REVISION:
        raise SystemExit("Use the Prosa v0.6 checkout at " + REVISION)
    env = os.environ.copy()
    env["PATH"] = str(rocq.parent) + os.pathsep + env["PATH"]
    graph = dependency_graph(root, rocq, env)
    required = set()
    remaining = [name + ".vo" for name in MODULES]
    while remaining:
        name = remaining.pop()
        if name in required:
            continue
        if name not in graph:
            raise SystemExit("Missing Prosa dependency: " + name)
        required.add(name)
        remaining.extend(graph[name])
    print(f"Building {len(required)} Prosa modules for POET", flush=True)
    pending = {name: graph[name].copy() for name in required}

    def compile_module(name):
        source = name.removesuffix(".vo") + ".v"
        if (root / name).is_file() and (root / name).stat().st_mtime >= max(
            (root / file).stat().st_mtime for file in {source, *graph[name]}
        ):
            return
        result = subprocess.run(
            [str(rocq), "compile", "-q", "-R", ".", "prosa", source],
            cwd=root, env=env, capture_output=True, encoding="utf-8", errors="replace"
        )
        if result.returncode:
            raise RuntimeError(source + "\n" + result.stdout + result.stderr)

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        running = {}
        done_count = 0
        while pending or running:
            ready = [name for name in sorted(pending) if not pending[name]]
            for name in ready[:max(0, jobs - len(running))]:
                del pending[name]
                running[pool.submit(compile_module, name)] = name
            if not running:
                raise RuntimeError("No buildable Prosa module found")
            completed, _ = wait(running, return_when=FIRST_COMPLETED)
            for future in completed:
                future.result()
                name = running.pop(future)
                done_count += 1
                if done_count % 25 == 0 or done_count == len(required):
                    print(f"{done_count}/{len(required)} Prosa modules ready", flush=True)
                for dependencies in pending.values():
                    dependencies.discard(name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prosa_root", type=Path)
    parser.add_argument("rocq", type=Path)
    parser.add_argument("--jobs", type=int, choices=range(1, 17), default=4)
    args = parser.parse_args()
    build(args.prosa_root.resolve(), args.rocq.resolve(), args.jobs)
