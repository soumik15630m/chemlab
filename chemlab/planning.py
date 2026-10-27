from __future__ import annotations

import math
import random
import time
from collections import Counter
from fractions import Fraction
from typing import Any, cast

from syntheseus import Molecule as SMolecule
from syntheseus.search.algorithms.best_first.retro_star import RetroStarSearch
from syntheseus.search.analysis.route_extraction import iter_routes_cost_order
from syntheseus.search.graph.and_or import AndNode, OrNode
from syntheseus.search.mol_inventory import BaseMolInventory
from syntheseus.search.node_evaluation.common import ConstantNodeEvaluator

from chemlab.adapters.models import ModelService, SearchModel
from chemlab.chemistry import require_molecule
from chemlab.records import (
    Occurrence,
    Route,
    RunConfig,
    SearchResult,
    Step,
    Stock,
    TerminationReason,
    canonical_bytes,
)


class ExactInventory(BaseMolInventory):
    def __init__(self, stock: Stock):
        self.identities = frozenset(stock.identities)

    def is_purchasable(self, mol: SMolecule) -> bool:
        return require_molecule(mol.smiles).canonical_smiles in self.identities


class CandidateCost:
    def __call__(self, nodes, graph=None):
        return [n.reaction.metadata["chemlab_cost"] for n in nodes]


def route_identity(route: Route) -> str:
    mols = {m.id: m for m in route.molecules}
    steps = {s.product_id: s for s in route.steps}

    def branch(mid: str, ancestors: frozenset[str]) -> Any:
        if mid in ancestors:
            raise ValueError("Occurrence cycle in route identity")
        identity = mols[mid].molecule.canonical_smiles
        step = steps.get(mid)
        if step is None:
            return [identity, None]
        children = {
            canonical_bytes(branch(child, ancestors | {mid})).decode("ascii")
            for child in step.precursor_ids
        }
        return [identity, sorted(children)]

    return canonical_bytes(branch(route.root_id, frozenset())).decode("ascii")


def extract_route(graph, nodes, source: str) -> Route:
    chosen = set(nodes)
    molecules: list[Occurrence] = []
    steps: list[Step] = []
    total_cost = 0.0

    def visit(node: OrNode, ancestors: frozenset[str]) -> str:
        nonlocal total_cost
        identity = require_molecule(node.mol.smiles)
        if identity.canonical_smiles in ancestors:
            raise ValueError("Molecular ancestor recurrence during route export")
        mid = f"m{len(molecules)}"
        molecules.append(Occurrence(id=mid, molecule=identity))
        selected = [n for n in graph.successors(node) if n in chosen]
        if len(selected) > 1:
            raise ValueError("Multiple selected reactions for a molecule")
        if selected:
            reaction = selected[0]
            children = sorted(graph.successors(reaction), key=lambda n: n.mol.smiles)
            precursors = tuple(visit(n, ancestors | {identity.canonical_smiles}) for n in children)
            total_cost += reaction.reaction.metadata["chemlab_cost"]
            steps.append(
                Step(
                    id=f"s{len(steps)}",
                    product_id=mid,
                    precursor_ids=precursors,
                    prediction_ref=reaction.reaction.metadata["prediction_ref"],
                    candidate_index=reaction.reaction.metadata["candidate_index"],
                )
            )
        return mid

    root = visit(graph.root_node, frozenset())
    return Route(
        root_id=root,
        molecules=tuple(molecules),
        steps=tuple(steps),
        search_cost=total_cost,
        source=source,
    )


class BudgetedRetroStar(RetroStarSearch):
    def __init__(self, config: RunConfig, model: SearchModel, **kwargs):
        self.config = config
        self.model = model
        self.reason: TerminationReason | None = None
        self.specific_limit: str | None = None
        self.started = time.monotonic()
        self.discovered: dict[str, Route] = {}
        self.discoveries: Counter[str] = Counter()
        self.provenance: dict[str, list[Route]] = {}
        self.last_nodes = -1
        super().__init__(reaction_model=model, **kwargs)

    def stable_node_key(self, node, graph):
        path = []
        while True:
            if isinstance(node, AndNode):
                label = canonical_bytes(
                    [
                        "reaction",
                        node.reaction.product.smiles,
                        sorted(m.smiles for m in node.reaction.reactants),
                    ]
                ).decode("ascii")
            else:
                label = canonical_bytes(["molecule", node.mol.smiles]).decode("ascii")
            path.append(label)
            parents = list(graph.predecessors(node))
            if not parents:
                break
            if len(parents) != 1:
                raise ValueError("Baseline search requires occurrence-tree parents")
            node = parents[0]
        return tuple(reversed(path))

    def visit_node(self, node, graph):
        return sorted(super().visit_node(node, graph), key=lambda n: self.stable_node_key(n, graph))

    def set_node_values(self, nodes, graph):
        return sorted(
            super().set_node_values(nodes, graph), key=lambda n: self.stable_node_key(n, graph)
        )

    def collect(self, graph) -> None:
        if len(graph) == self.last_nodes:
            return
        self.last_nodes = len(graph)
        if not graph.root_node.has_solution:
            return
        for node in graph.nodes():
            cost = (
                cast(dict[str, Any], node.reaction.metadata)["chemlab_cost"]
                if isinstance(node, AndNode)
                else 0.0
            )
            cast(dict[str, Any], node.data)["route_cost"] = Fraction.from_float(float(cost))
        for nodes in iter_routes_cost_order(graph, max_routes=2**31 - 1):
            if any(isinstance(n, OrNode) and not n.has_solution for n in nodes):
                continue
            route = extract_route(graph, nodes, self.model.service.manifest.name)
            identity = route_identity(route)
            if identity not in self.discovered:
                self.discovered[identity] = route
                self.discoveries[identity] += 1
                self.provenance[identity] = [route]
            elif route not in self.provenance[identity]:
                self.provenance[identity].append(route)
                self.discoveries[identity] += 1
                if route.search_cost < self.discovered[identity].search_cost:
                    self.discovered[identity] = route
            if len(self.discovered) >= self.config.route_limit:
                break

    def should_stop_search(self, graph) -> bool:
        self.collect(graph)
        if len(self.discovered) >= self.config.route_limit:
            self.reason = "requested_route_count_reached"
            return True
        limits = [
            (
                "logical_expansion_limit",
                self.model.logical_expansions >= self.config.logical_expansion_limit,
            ),
            (
                "actual_inference_limit",
                self.config.actual_inference_limit is not None
                and self.model.service.actual_inferences >= self.config.actual_inference_limit,
            ),
            (
                "time_limit_seconds",
                self.config.time_limit_seconds is not None
                and time.monotonic() - self.started >= self.config.time_limit_seconds,
            ),
        ]
        for name, exhausted in limits:
            if exhausted:
                self.reason, self.specific_limit = "budget_exhausted", name
                return True
        return False


def search(target: str, config: RunConfig, service: ModelService, stock: Stock) -> SearchResult:
    target = require_molecule(target).canonical_smiles
    model = SearchModel(service, config.prediction_count)
    if target in stock.identities:
        route = Route(
            root_id="m0",
            molecules=(Occurrence(id="m0", molecule=require_molecule(target)),),
            steps=(),
            search_cost=0,
            source=service.manifest.name,
        )
        return SearchResult(
            routes=(route,),
            termination_reason="already_in_stock",
            candidate_routes_found=1,
            duplicate_discoveries=0,
            logical_expansions=0,
            actual_inferences=0,
            cache_hits=0,
        )
    algorithm = BudgetedRetroStar(
        config,
        model,
        mol_inventory=ExactInventory(stock),
        value_function=ConstantNodeEvaluator(0),
        and_node_cost_fn=CandidateCost(),
        limit_iterations=2**31 - 1,
        limit_reaction_model_calls=2**31 - 1,
        time_limit_s=math.inf,
        max_expansion_depth=config.max_depth * 2,
        unique_nodes=False,
        prevent_repeat_mol_in_trees=True,
        stop_on_first_solution=False,
        random_state=random.Random(config.seed),
    )
    error = None
    try:
        graph, _ = algorithm.run_from_mol(SMolecule(target))
        algorithm.collect(graph)
        algorithm.should_stop_search(graph)
    except Exception as exc:
        algorithm.reason, error = "execution_error", str(exc)
    routes = tuple(
        sorted(algorithm.discovered.values(), key=lambda r: (r.search_cost, route_identity(r)))
    )
    return SearchResult(
        routes=routes,
        termination_reason=algorithm.reason or "candidate_space_exhausted",
        exhausted_limit=algorithm.specific_limit,
        candidate_routes_found=len(routes),
        duplicate_discoveries=sum(algorithm.discoveries.values()) - len(routes),
        logical_expansions=model.logical_expansions,
        actual_inferences=service.actual_inferences,
        cache_hits=service.cache_hits + int(model.num_calls(count_cache=True) - model.num_calls()),
        prediction_refs=tuple(sorted(set(model.prediction_refs))),
        error=error,
    )
