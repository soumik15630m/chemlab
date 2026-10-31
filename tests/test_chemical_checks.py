from copy import deepcopy

from chemlab.evidence.chemical_checks import assess_reaction, validate_mapping

QUERY = {"product": "CC=O", "precursors": ["CCO"]}
PROPOSAL = {
    "input": QUERY,
    "input_key": "f1e93a4a78932a3b14226d35b3161078f1eb4e8973bbe68c4d0e203bbe9b5da8",
    "status": "ok",
    "raw_prediction": {"mapped_rxn": "[CH3:1][CH2:2][OH:3]>>[CH3:1][CH:2]=[O:3]"},
}


def test_listed_atom_obligation_has_positive_negative_and_unknown_controls():
    missing = assess_reaction("CN", ("C",))
    assert missing["evidence_outcome"] == "contradiction"
    assert missing["checks"]["listed_atom_sources"]["status"] == "fail"
    assert missing["chemical_feasibility"] == "unresolved"
    present = assess_reaction("CN", ("C", "N"))
    assert present["checks"]["listed_atom_sources"]["status"] == "pass"
    assert present["evidence_outcome"] == "unresolved"
    # Coefficients are absent: carbon counts cannot establish a contradiction.
    counts = assess_reaction("CC", ("C",))
    assert counts["evidence_outcome"] == "unresolved"
    assert counts["checks"]["stoichiometry"]["status"] == "unknown"
    assert assess_reaction("[13CH3]O", ("CO",))["evidence_outcome"] == "contradiction"
    assert assess_reaction("[13CH3]O", ("[13CH3]O",))["evidence_outcome"] == "unresolved"
    assert assess_reaction("[2H]C", ("C",))["evidence_outcome"] == "contradiction"
    assert assess_reaction("[2H]C", ("C", "[2H]O"))["evidence_outcome"] == "unresolved"
    assert assess_reaction("[2H]C", ("C", "[3H]O"))["evidence_outcome"] == "contradiction"


def test_validated_mapping_supplies_edits_but_never_feasibility():
    result = assess_reaction("CC=O", ("CCO",), proposal=PROPOSAL)
    assert result["checks"]["mapping"]["status"] == "pass"
    assert result["checks"]["edits"]["status"] == "observed"
    assert result["evidence_outcome"] == "unresolved"
    assert result["chemical_feasibility"] == "unresolved"
    assert result["checks"]["conditions"]["status"] == "not_checked"


def test_misbound_element_incompatible_partial_and_error_maps_cannot_supply_edits():
    bad = deepcopy(PROPOSAL)
    bad["input_key"] = "0" * 64
    assert validate_mapping(QUERY, bad)["status"] == "fail"
    bad = deepcopy(PROPOSAL)
    bad["raw_prediction"]["mapped_rxn"] = "[CH3:1][CH:2]=[O:3]>>[CH3:1][CH2:2][OH:3]"
    assert validate_mapping(QUERY, bad)["reason"] == "mapped_reaction_identity_mismatch"
    bad = deepcopy(PROPOSAL)
    bad["raw_prediction"]["mapped_rxn"] = "[CH3:3][CH2:2][OH:1]>>[CH3:1][CH:2]=[O:3]"
    assert validate_mapping(QUERY, bad)["status"] == "fail"
    assert assess_reaction("CC=O", ("CCO",), proposal=bad)["checks"]["edits"]["status"] == "unknown"
    bad["raw_prediction"]["mapped_rxn"] = "CCO>>CC=O"
    assert validate_mapping(QUERY, bad)["status"] == "unknown"
    bad["status"] = "error"
    assert assess_reaction("CC=O", ("CCO",), proposal=bad)["evidence_outcome"] == "error"


def test_tool_failure_is_visible_and_never_evidence_support():
    class BrokenLibrary:
        def lookup(self, *args, **kwargs):
            raise TimeoutError("contract test seeded tool failure")

    result = assess_reaction("CC=O", ("CCO",), library=BrokenLibrary())
    assert result["evidence_outcome"] == "error"
    assert result["checks"]["exact_precedent"]["status"] == "error"
