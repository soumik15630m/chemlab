"""Run with Python 3.11+: python start_docker.py (or use docker compose up --build)."""

from chemlab.bootstrap import docker_main, run

if __name__ == "__main__":
    raise SystemExit(run(docker_main))
