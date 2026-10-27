import itertools

import networkx as nx

from chemlab.chemistry import require_molecule
from chemlab.records import Occurrence, Route, Step
from chemlab.verification import verify


def test_all_directed_graphs_up_to_three_occurrences(lab):
    store, config, *_ = lab
    tested = 0
    for size in range(1, 4):
        edges = list(itertools.product(range(size), repeat=2))
        labelings = [list(range(size)), [0] * size]
        if size == 3:
            labelings.append([0, 1, 0])
        for labels in labelings:
            identities = ["C" * (label + 1) for label in labels]
            molecules = tuple(
                Occurrence(id=f"m{i}", molecule=require_molecule(s))
                for i, s in enumerate(identities)
            )
            for bitmask in range(1 << len(edges)):
                selected = [edge for bit, edge in enumerate(edges) if bitmask & (1 << bit)]
                graph = nx.DiGraph()
                graph.add_nodes_from(range(size))
                graph.add_edges_from(selected)
                expected = nx.is_arborescence(graph) and graph.in_degree(0) == 0
                if expected:
                    for target in range(1, size):
                        path = nx.shortest_path(graph, 0, target)
                        if len({identities[node] for node in path}) != len(path):
                            expected = False
                            break
                steps = []
                for product in range(size):
                    children = sorted(graph.successors(product))
                    if children:
                        steps.append(
                            Step(
                                id=f"s{product}",
                                product_id=f"m{product}",
                                precursor_ids=tuple(f"m{i}" for i in children),
                                prediction_ref="0" * 64,
                                candidate_index=0,
                            )
                        )
                route = Route(
                    root_id="m0",
                    molecules=molecules,
                    steps=tuple(steps),
                    search_cost=0,
                    source="bounded computational experiment",
                )
                result = verify(store, route.model_dump(mode="json"), identities[0], config)
                graph_check = next(c for c in result.checks if c.name == "graph")
                assert (graph_check.status == "pass") == expected, (size, labels, selected)
                tested += 1
    assert tested == 1572
