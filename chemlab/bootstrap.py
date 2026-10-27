"""First-run setup shared by the native and container launchers."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import venv
from collections.abc import Callable
from pathlib import Path


def runtime_environment(root: Path) -> dict[str, str]:
    return {
        **os.environ,
        "PYTHONPATH": str(root),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
        "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS", "2"),
        "MKL_NUM_THREADS": os.environ.get("MKL_NUM_THREADS", "2"),
        "WANDB_MODE": "disabled",
        "PIP_DEFAULT_TIMEOUT": os.environ.get("PIP_DEFAULT_TIMEOUT", "120"),
        "PIP_RETRIES": os.environ.get("PIP_RETRIES", "10"),
    }


def virtual_python(directory: Path, platform: str) -> Path:
    return directory / ("Scripts/python.exe" if platform == "win32" else "bin/python")


def native_requirements(text: str, platform: str) -> str:
    # macOS publishes the same Torch release without the Linux/Windows CPU suffix.
    return text.replace("torch==2.14.1+cpu", "torch==2.14.1") if platform == "darwin" else text


def prepare(root: Path, state: Path) -> None:
    env = runtime_environment(root)
    print("Preparing models, stock and public precedent. First use needs several GB.", flush=True)
    subprocess.run(
        [sys.executable, str(root / "scripts" / "fetch_pretrained.py")],
        cwd=root,
        env=env,
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "chemlab",
            "--store",
            str(state),
            "setup-pretrained",
            "--models",
            str(root / "models"),
        ],
        cwd=root,
        env=env,
        check=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--state", type=Path, default=Path("var/docker"))
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args(argv)
    root, state = args.root.resolve(), args.state.resolve()
    prepare(root, state)
    if args.prepare_only:
        return 0
    print(f"Starting ChemLab at http://127.0.0.1:{args.port}", flush=True)
    return subprocess.call(
        [
            sys.executable,
            "-m",
            "chemlab",
            "--store",
            str(state),
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            str(args.port),
        ],
        cwd=root,
        env=runtime_environment(root),
    )


def native_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a local venv, prepare data and start ChemLab"
    )
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--venv", type=Path, default=root / ".venv")
    parser.add_argument("--state", type=Path, default=root / "var" / "local")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args(argv)
    if sys.version_info < (3, 11):  # noqa: UP036 - launcher runs before package installation
        parser.error("Python 3.11 or newer is required; Python 3.11 is the tested runtime")
    directory = args.venv.resolve()
    python = virtual_python(directory, sys.platform)
    if not directory.exists():
        print(f"Creating virtual environment: {directory}", flush=True)
        venv.EnvBuilder(with_pip=True).create(directory)
    if not (directory / "pyvenv.cfg").is_file() or not python.is_file():
        parser.error(f"{directory} is not a complete virtual environment; choose --venv PATH")
    env = {**runtime_environment(root), "PIP_REQUIRE_VIRTUALENV": "true"}
    # Reused uv environments may have no pip. Bootstrap only inside the selected venv.
    subprocess.run([str(python), "-m", "ensurepip", "--upgrade"], env=env, check=True)
    lock = directory / "chemlab-requirements.lock"
    lock.write_text(
        native_requirements((root / "requirements.lock").read_text(encoding="ascii"), sys.platform),
        encoding="ascii",
    )
    subprocess.run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--extra-index-url",
            "https://download.pytorch.org/whl/cpu",
            "-r",
            str(lock),
        ],
        cwd=root,
        env=env,
        check=True,
    )
    command = [
        str(python),
        "-m",
        "chemlab.bootstrap",
        "--root",
        str(root),
        "--state",
        str(args.state.resolve()),
        "--port",
        str(args.port),
    ]
    if args.prepare_only:
        command.append("--prepare-only")
    return subprocess.call(command, cwd=root, env=env)


def docker_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build, initialize and start ChemLab with Compose")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--detach", action="store_true")
    args = parser.parse_args(argv)
    docker = shutil.which("docker")
    if not docker:
        parser.error("Docker was not found. Install/start Docker Desktop, or use start_venv.py")
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "CHEMLAB_PORT": str(args.port)}
    subprocess.run([docker, "compose", "version"], cwd=root, env=env, check=True)
    command = [docker, "compose", "up", "--build"]
    if args.detach:
        command.extend(["--detach", "--wait", "--wait-timeout", "1800"])
    return subprocess.call(command, cwd=root, env=env)


def run(entrypoint: Callable[[], int]) -> int:
    try:
        return entrypoint()
    except KeyboardInterrupt:
        return 130
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Startup failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run(main))
