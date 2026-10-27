import pytest

from chemlab.chemistry import identify, require_molecule
from chemlab.chemistry.identity import mapping_status, stereo_relation
from chemlab.records import MoleculeError


@pytest.mark.parametrize(
    "left,right,equal",
    [
        ("OCC", "CCO", True),
        ("[CH3:7][OH:9]", "CO", True),
        ("[Na+].[Cl-]", "[Cl-].[Na+]", True),
        ("[13CH4]", "C", False),
        ("[NH4+]", "N", False),
        ("CCO.[Na+]", "CCO", False),
        ("C[C@H](O)Cl", "C[C@@H](O)Cl", False),
        ("CC(O)Cl", "C[C@H](O)Cl", False),
        ("CC(=O)C", "CC(O)=C", False),
        ("F/C=C/F", "F/C=C\\F", False),
    ],
)
def test_identity_contract(left, right, equal):
    assert (
        require_molecule(left).canonical_smiles == require_molecule(right).canonical_smiles
    ) is equal
    identity = require_molecule(left).canonical_smiles
    assert require_molecule(identity).canonical_smiles == identity


@pytest.mark.parametrize("smiles", ["", "invalid", "C1CC", "*C"])
def test_errors_have_no_invented_identity(smiles):
    result = identify(smiles)
    assert isinstance(result, MoleculeError)
    assert "canonical_smiles" not in result.model_dump()


@pytest.mark.parametrize(
    "left,right,relation",
    [
        ("CCO", "OCC", "exact"),
        ("C[C@H](O)Cl", "C[C@@H](O)Cl", "different"),
        ("C[C@H](O)Cl", "CC(O)Cl", "compatible_missing_stereo"),
        ("CC(O)Cl", "C[C@@H](O)Cl", "compatible_missing_stereo"),
        ("F/C=C/F", "F/C=C\\F", "different"),
        ("FC=CF", "F/C=C/F", "compatible_missing_stereo"),
        ("[13CH4]", "C", "different"),
        ("C[C@H](O)[C@H](F)Cl", "C[C@@H](O)C(F)Cl", "different"),
    ],
)
def test_forward_stereo_constraints(left, right, relation):
    assert stereo_relation(left, right) == relation


@pytest.mark.parametrize(
    "mapped,status",
    [
        (None, "unknown"),
        ("[CH3:1][OH:2]>>[CH2:1]=[O:2]", "pass"),
        ("[CH3:1][OH:1]>>[CH2:1]=[O:2]", "fail"),
        ("[CH3:1][OH:2]>>[CH2:2]=[O:1]", "fail"),
        ("CO>>C=O", "unknown"),
        ("[13CH3:1][OH:2]>>[CH2:1]=[O:2]", "fail"),
    ],
)
def test_mapping_policy(mapped, status):
    assert mapping_status(mapped)[0] == status
