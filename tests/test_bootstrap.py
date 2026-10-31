import subprocess
from pathlib import Path

import pytest
import yaml

from chemlab import bootstrap
from scripts.setup_reaction_knowledge import mapper_command


def test_mapper_interpreter_symlink_keeps_the_selected_virtual_environment(tmp_path):
    base = tmp_path / "base-python"
    base.write_text("base interpreter", encoding="ascii")
    selected = tmp_path / "mapping-venv" / "bin" / "python"
    selected.parent.mkdir(parents=True)
    selected.symlink_to(base)
    assert mapper_command(selected) == (
        str(selected),
        "-m",
        "chemlab.evidence.mapping_worker",
    )
    assert mapper_command(selected)[0] != str(base)


def test_compose_initialization_gate_and_persistent_mounts():
    source = Path(bootstrap.__file__).resolve().parents[1] / "compose.yaml"
    services = yaml.safe_load(source.read_text(encoding="ascii"))["services"]
    setup, app = services["setup"], services["chemlab"]
    assert setup["build"]["target"] == "pretrained"
    assert "build" not in app
    assert app["image"] == setup["image"]
    assert app["pull_policy"] == "never"
    assert app["depends_on"]["setup"]["condition"] == "service_completed_successfully"
    assert "./models:/workspace/models" in setup["volumes"]
    assert "./models:/workspace/models:ro" in app["volumes"]
    assert "./var/docker:/workspace/var" in setup["volumes"]
    assert "./var/docker:/workspace/var" in app["volumes"]
    assert "./var/reaction-data:/workspace/reaction-data" in setup["volumes"]
    assert "./var/reaction-data:/workspace/reaction-data:ro" in app["volumes"]
    assert app["read_only"] is True
    assert app["ports"] == ["127.0.0.1:${CHEMLAB_PORT:-8080}:8080"]


@pytest.mark.parametrize(
    ("platform", "relative"),
    [("win32", "Scripts/python.exe"), ("linux", "bin/python"), ("darwin", "bin/python")],
)
def test_platform_interpreter_stays_inside_selected_venv(tmp_path, platform, relative):
    directory = tmp_path / "path with spaces"
    assert bootstrap.virtual_python(directory, platform) == directory / relative


def test_native_pin_changes_only_macos_torch_build():
    lock = "numpy==2.4.6\ntorch==2.14.1+cpu\nrdkit==2026.9.1\n"
    assert bootstrap.native_requirements(lock, "linux") == lock
    assert bootstrap.native_requirements(lock, "win32") == lock
    assert bootstrap.native_requirements(lock, "darwin") == (
        "numpy==2.4.6\ntorch==2.14.1\nrdkit==2026.9.1\n"
    )


def test_failed_preparation_never_starts_web_service(monkeypatch, tmp_path):
    launched = []

    def fail(*args):
        raise subprocess.CalledProcessError(7, ["setup-pretrained"])

    monkeypatch.setattr(bootstrap, "prepare", fail)
    monkeypatch.setattr(bootstrap.subprocess, "call", lambda *a, **kw: launched.append(a))
    with pytest.raises(subprocess.CalledProcessError):
        bootstrap.main(["--root", str(tmp_path), "--state", str(tmp_path / "state")])
    assert launched == []


def test_prepare_only_has_no_server_side_effect(monkeypatch, tmp_path):
    prepared, launched = [], []
    monkeypatch.setattr(bootstrap, "prepare", lambda *a: prepared.append(a))
    monkeypatch.setattr(bootstrap.subprocess, "call", lambda *a, **kw: launched.append(a))
    assert bootstrap.main(["--root", str(tmp_path), "--prepare-only"]) == 0
    assert len(prepared) == 1
    assert prepared[0][0] == tmp_path
    assert launched == []


def test_download_failure_blocks_registration(monkeypatch, tmp_path):
    commands = []

    def execute(command, **kwargs):
        commands.append(command)
        if kwargs.get("check"):
            raise subprocess.CalledProcessError(1, command)
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(bootstrap.subprocess, "run", execute)
    with pytest.raises(subprocess.CalledProcessError):
        bootstrap.prepare(tmp_path, tmp_path / "state")
    assert len(commands) == 1
    assert Path(commands[0][1]).name == "fetch_pretrained.py"


def test_missing_or_failed_knowledge_preparation_blocks_model_registration(monkeypatch, tmp_path):
    commands = []
    monkeypatch.delenv("CHEMLAB_MAPPER_PYTHON", raising=False)
    monkeypatch.setattr(bootstrap.subprocess, "run", lambda command, **kw: commands.append(command))
    with pytest.raises(RuntimeError, match="mapping runtime"):
        bootstrap.prepare(tmp_path, tmp_path / "state")
    assert len(commands) == 1
    commands.clear()
    monkeypatch.setenv("CHEMLAB_MAPPER_PYTHON", "/isolated/mapper/python")

    def fail_knowledge(command, **kwargs):
        commands.append(command)
        if "setup_reaction_knowledge.py" in command[1]:
            raise subprocess.CalledProcessError(19, command)

    monkeypatch.setattr(bootstrap.subprocess, "run", fail_knowledge)
    with pytest.raises(subprocess.CalledProcessError):
        bootstrap.prepare(tmp_path, tmp_path / "state")
    assert len(commands) == 2
    assert all("setup-pretrained" not in command for command in commands)


def test_native_installs_and_runs_only_selected_virtual_interpreter(monkeypatch, tmp_path):
    root = tmp_path / "checkout with spaces"
    root.mkdir()
    (root / "requirements.lock").write_text(
        "torch==2.14.1+cpu\nsetuptools==84.2.1\n", encoding="ascii"
    )
    (root / "requirements-mapping.lock").write_text(
        "rxnmapper==0.4.2\nsetuptools==80.9.0\n", encoding="ascii"
    )
    monkeypatch.setattr(bootstrap, "__file__", str(root / "chemlab" / "bootstrap.py"))
    directory = tmp_path / "chosen venv"
    python = bootstrap.virtual_python(directory, bootstrap.sys.platform)
    python.parent.mkdir(parents=True)
    python.touch()
    (directory / "pyvenv.cfg").write_text("home = /example", encoding="ascii")
    mapping_directory = directory.with_name(directory.name + "-mapping")
    mapping_python = bootstrap.virtual_python(mapping_directory, bootstrap.sys.platform)
    mapping_python.parent.mkdir(parents=True)
    mapping_python.touch()
    (mapping_directory / "pyvenv.cfg").write_text("home = /example", encoding="ascii")
    calls = []

    def execute(command, **kwargs):
        calls.append((command, kwargs))
        return 0

    monkeypatch.setattr(bootstrap.subprocess, "run", execute)
    monkeypatch.setattr(bootstrap.subprocess, "call", execute)
    assert bootstrap.native_main(["--venv", str(directory), "--port", "8123"]) == 0
    assert len(calls) == 4
    assert [command[0] for command, _ in calls] == [
        str(python),
        str(python),
        str(mapping_python),
        str(python),
    ]
    assert calls[0][0][1:] == ["-m", "ensurepip", "--upgrade"]
    assert calls[1][0][1:4] == ["-m", "pip", "install"]
    assert calls[1][1]["check"] is True
    assert all(options["env"]["PIP_REQUIRE_VIRTUALENV"] == "true" for _, options in calls)
    command, options = calls[-1]
    assert command[1:3] == ["-m", "chemlab.bootstrap"]
    assert command[command.index("--state") + 1] == str(root / "var" / "local")
    assert command[-2:] == ["--port", "8123"]
    assert options["cwd"] == root
    assert options["env"]["PYTHONPATH"] == str(root)
    assert options["env"]["CHEMLAB_MAPPER_PYTHON"] == str(mapping_python)
    assert (
        directory / "chemlab-requirements.lock"
    ).read_text() == "torch==2.14.1+cpu\nsetuptools==84.2.1\n"
    assert (
        mapping_directory / "chemlab-mapping.lock"
    ).read_text() == "torch==2.14.1+cpu\nrxnmapper==0.4.2\nsetuptools==80.9.0\n"


def test_incomplete_existing_directory_is_preserved(monkeypatch, tmp_path):
    directory = tmp_path / "existing"
    directory.mkdir()
    marker = directory / "keep.txt"
    marker.write_text("existing work", encoding="ascii")
    with pytest.raises(SystemExit, match="2"):
        bootstrap.native_main(["--venv", str(directory)])
    assert marker.read_text(encoding="ascii") == "existing work"


def test_detached_compose_waits_for_health_and_propagates_failure(monkeypatch):
    commands = []
    monkeypatch.setattr(bootstrap.shutil, "which", lambda _: "/usr/bin/docker")
    monkeypatch.setattr(bootstrap.subprocess, "run", lambda *a, **kw: None)

    def execute(command, **kwargs):
        commands.append((command, kwargs))
        return 5

    monkeypatch.setattr(bootstrap.subprocess, "call", execute)
    assert bootstrap.docker_main(["--detach", "--port", "8124"]) == 5
    command, options = commands[0]
    assert command[:4] == ["/usr/bin/docker", "compose", "up", "--build"]
    assert command[4:] == ["--detach", "--wait", "--wait-timeout", "14400"]
    assert options["env"]["CHEMLAB_PORT"] == "8124"


def test_startup_error_is_nonzero_and_explained(capsys):
    def fail():
        raise OSError("missing shared library")

    assert bootstrap.run(fail) == 1
    assert "missing shared library" in capsys.readouterr().err
