from chemlab.adapters.models import ModelService
from chemlab.evidence.checks import import_stock, load_stock
from chemlab.planning import route_identity, search


def test_one_valid_chain(lab):
    store, config, _, service, _ = lab
    result = search("CCOC(C)=O", config, service, load_stock(store, config.stock_ref))
    assert result.error is None
    assert result.candidate_routes_found == 1
    assert len(result.routes[0].steps) == 1
    assert result.logical_expansions == 1
    assert len(result.prediction_refs) == 1
    assert store.prediction(result.prediction_refs[0])["status"] == "ok"


def test_failed_search_retains_its_inference_error_record(lab, monkeypatch):
    store, config, _, service, _ = lab

    def fail(*args):
        raise TimeoutError("synthetic backend failure")

    monkeypatch.setattr(service, "_raw", fail)
    result = search("CC", config, service, load_stock(store, config.stock_ref))
    assert result.termination_reason == "execution_error"
    assert len(result.prediction_refs) == 1
    assert store.prediction(result.prediction_refs[0])["status"] == "error"


def test_stocked_root(lab):
    store, config, _, service, _ = lab
    result = search("CCO", config, service, load_stock(store, config.stock_ref))
    assert result.termination_reason == "already_in_stock"
    assert result.routes[0].steps == ()
    assert result.logical_expansions == result.actual_inferences == 0


def test_missing_and_precursor_is_not_solved(lab):
    store, config, _, service, _ = lab
    ref = import_stock(store, ["CCO"], "Incomplete", "test", "test")
    result = search(
        "CCOC(C)=O", config.model_copy(update={"stock_ref": ref}), service, load_stock(store, ref)
    )
    assert result.candidate_routes_found == 0
    assert result.termination_reason == "candidate_space_exhausted"


def test_budget_reports_routes_already_found(lab):
    store, config, _, service, _ = lab
    cfg = config.model_copy(update={"logical_expansion_limit": 1})
    result = search("CCOC(C)=O", cfg, service, load_stock(store, cfg.stock_ref))
    assert result.termination_reason == "budget_exhausted"
    assert result.exhausted_limit == "logical_expansion_limit"
    assert result.candidate_routes_found == 1


def test_route_count_is_candidate_identity_count(lab):
    store, config, _, service, _ = lab
    result = search(
        "CCOC(C)=O",
        config.model_copy(update={"route_limit": 1}),
        service,
        load_stock(store, config.stock_ref),
    )
    assert result.termination_reason == "requested_route_count_reached"
    assert result.candidate_routes_found == 1


def test_cycle_does_not_solve(lab):
    store, config, register, _, _ = lab
    ref = register(
        {
            "CC": [{"precursors": ["CCC"], "score": 0.9}],
            "CCC": [{"precursors": ["CC"], "score": 0.9}],
        }
    )
    cfg = config.model_copy(update={"backward_manifest": ref})
    result = search("CC", cfg, ModelService(store, ref), load_stock(store, cfg.stock_ref))
    assert result.candidate_routes_found == 0
    assert result.logical_expansions == 2


def test_shared_intermediate_uses_distinct_occurrences(lab):
    store, config, register, _, _ = lab
    ref = register(
        {
            "CCCC": [{"precursors": ["CC", "CCC"], "score": 0.9}],
            "CC": [{"precursors": ["CO"], "score": 0.9}],
            "CCC": [{"precursors": ["CO"], "score": 0.9}],
        }
    )
    stock_ref = import_stock(store, ["CO"], "Test", "test", "test")
    cfg = config.model_copy(update={"backward_manifest": ref, "stock_ref": stock_ref})
    result = search("CCCC", cfg, ModelService(store, ref), load_stock(store, stock_ref))
    assert result.error is None
    assert result.candidate_routes_found == 1
    route = result.routes[0]
    same = [m for m in route.molecules if m.molecule.canonical_smiles == "CO"]
    assert len(same) == 2 and same[0].id != same[1].id
    from chemlab.verification import verify

    assert verify(store, route.model_dump(mode="json"), "CCCC", cfg).structural_status == "verified"


def test_route_identity_ignores_ids_order_and_source(ester_route):
    altered = ester_route.model_copy(
        update={
            "source": "another model",
            "molecules": tuple(reversed(ester_route.molecules)),
            "steps": (ester_route.steps[0].model_copy(update={"precursor_ids": ("m2", "m1")}),),
        }
    )
    assert route_identity(ester_route) == route_identity(altered)
