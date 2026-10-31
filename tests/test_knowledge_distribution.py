import json
import zipfile

import pytest

from chemlab.evidence.knowledge_distribution import export_knowledge, restore_knowledge
from chemlab.evidence.reaction_library import HEADER, ReactionLibrary, build_library, file_digest
from chemlab.evidence.reaction_templates import ContextLibrary, build_context_library
from chemlab.store import IntegrityError
from scripts.setup_reaction_knowledge import publication_path


@pytest.fixture
def knowledge(tmp_path):
    raw = tmp_path / "source.rsmi"
    raw.write_text(HEADER + "\n[CH3:1][CH2:2][OH:3]>>[CH3:1][CH:2]=[O:3]\tUS-fixture\t1\t2000\n")
    source_path = tmp_path / "source-index"
    build_library(
        [
            {
                "id": "software-fixture",
                "path": str(raw),
                "sha256": file_digest(raw),
                "kind": "reported_patent",
                "partition": "training",
            }
        ],
        source_path,
    )
    source = ReactionLibrary(source_path, file_digest(source_path / "manifest.json"))
    context_path = tmp_path / "context-index"
    build_context_library(source, context_path)
    contexts = ContextLibrary(context_path, file_digest(context_path / "manifest.json"), source)
    return source, contexts


def test_downloadable_knowledge_roundtrips_exact_bytes_and_references(knowledge, tmp_path):
    source, contexts = knowledge
    archive = tmp_path / "knowledge.zip"
    result = export_knowledge(source, contexts, archive)
    duplicate = tmp_path / "identical.zip"
    assert export_knowledge(source, contexts, duplicate) == result
    assert archive.read_bytes() == duplicate.read_bytes()
    restored = restore_knowledge(archive, result["sha256"], tmp_path / "restored")
    from pathlib import Path

    copied_source = ReactionLibrary(Path(restored["source"]), source.manifest_ref)
    copied_context = ContextLibrary(
        Path(restored["contexts"]), contexts.manifest_ref, copied_source
    )
    assert copied_source.lookup("CC=O", ("CCO",)) == source.lookup("CC=O", ("CCO",))
    mapped = "[CH3:1][CH2:2][OH:3]>>[CH3:1][CH:2]=[O:3]"
    assert copied_context.lookup(mapped, "CC=O", ("CCO",)) == contexts.lookup(
        mapped, "CC=O", ("CCO",)
    )
    for name in ("reactions.sqlite3", "manifest.json", "complete.json"):
        assert (copied_source.root / name).read_bytes() == (source.root / name).read_bytes()
    again = restore_knowledge(archive, result["sha256"], tmp_path / "restored")
    assert again["source"] != restored["source"]
    assert copied_source.lookup("CC=O", ("CCO",))["status"] == "reported_match"
    assert publication_path(tmp_path / "restored/libraries", "source-index").exists()


def test_incomplete_corrupt_or_pointer_archives_cannot_publish_knowledge(knowledge, tmp_path):
    source, contexts = knowledge
    archive = tmp_path / "knowledge.zip"
    result = export_knowledge(source, contexts, archive)
    with pytest.raises(IntegrityError, match="archive hash"):
        restore_knowledge(archive, "0" * 64, tmp_path / "bad")
    with pytest.raises(FileExistsError):
        export_knowledge(source, contexts, archive)
    pointer = tmp_path / "pointer.zip"
    pointer.write_bytes(b"version https://git-lfs.github.com/spec/v1\noid sha256:fake\n")
    with pytest.raises(ValueError, match="git lfs pull"):
        restore_knowledge(pointer, "0" * 64, tmp_path / "pointer-output")
    damaged = tmp_path / "damaged.zip"
    with zipfile.ZipFile(archive) as original, zipfile.ZipFile(damaged, "w") as output:
        for name in original.namelist():
            data = original.read(name)
            if name == "contexts/contexts.sqlite3":
                data = data[:-1] + bytes([data[-1] ^ 1])
            output.writestr(name, data)
    with pytest.raises(IntegrityError, match="member hash"):
        restore_knowledge(damaged, file_digest(damaged), tmp_path / "damaged-output")
    assert not list((tmp_path / "damaged-output").glob("contexts/*/complete.json"))
    assert result["package"]["source_ref"] == source.manifest_ref


def test_archive_members_cannot_escape_the_declared_contract(tmp_path):
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(
            "package.json",
            json.dumps({"version": "reaction-knowledge-archive-v1", "files": {"../escaped": {}}}),
        )
        output.writestr("../escaped", b"not allowed")
    with pytest.raises(IntegrityError, match="members"):
        restore_knowledge(archive, file_digest(archive), tmp_path / "restore")
    assert not (tmp_path / "escaped").exists()


def test_corrupt_source_index_cannot_be_packaged_as_complete(knowledge, tmp_path):
    source, contexts = knowledge
    source.database.write_bytes(b"corrupt")
    output = tmp_path / "forbidden.zip"
    with pytest.raises(IntegrityError, match="changed before packaging"):
        export_knowledge(source, contexts, output)
    assert not output.exists()
