import pytest
from pydantic import ValidationError

from evidenceops.domain.enums import Action
from evidenceops.domain.state import EvidenceOpsState
from evidenceops.graph import nodes
from evidenceops.graph.routing import route_after_decision
from evidenceops.graph.service import QueryRequest, QueryService
from evidenceops.graph.workflow import build_evidenceops_graph


@pytest.mark.parametrize(
    "name",
    [
        "initialize",
        "extract_features",
        "controller_decide",
        "retrieve",
        "rerank",
        "evaluate_evidence",
        "reformulate",
        "generate",
        "validate_citations",
        "abstain",
        "finalize",
    ],
)
def test_every_node_rejects_invalid_counters(name):
    state = EvidenceOpsState(run_id="r", original_query="q", active_query="q").to_langgraph_dict()
    state["retrieval_calls"] = 4
    with pytest.raises(ValidationError):
        getattr(nodes, name + "_node")(state)


def test_node_adapter_validates_output_too():
    @nodes.validated_node
    def corrupt(state):
        state["metadata"]["generation_attempts"] = 3
        return state

    with pytest.raises(ValidationError):
        corrupt(
            EvidenceOpsState(run_id="r", original_query="q", active_query="q").to_langgraph_dict()
        )


@pytest.mark.parametrize(
    "action,expected",
    [
        (Action.DIRECT_ANSWER, "generate"),
        (Action.STOP, "generate"),
        (Action.RETRIEVE_SPARSE, "retrieve"),
        (Action.RETRIEVE_DENSE, "retrieve"),
        (Action.RETRIEVE_HYBRID, "retrieve"),
        (Action.REFORMULATE, "reformulate"),
        (Action.ABSTAIN, "abstain"),
        (Action.RERANK, "abstain"),
        (None, "abstain"),
    ],
)
def test_all_controller_actions_have_a_bounded_route(action, expected):
    state = EvidenceOpsState(run_id="r", original_query="q", active_query="q", next_action=action)
    assert route_after_decision(state.to_langgraph_dict()) == expected


def test_topology_keeps_all_nodes_and_terminal_edges():
    graph = build_evidenceops_graph().get_graph()
    assert len(graph.nodes) == 13  # Eleven explicit nodes plus start and end.
    edges = {(e.source, e.target) for e in graph.edges}
    assert {
        ("abstain", "__end__"),
        ("finalize", "__end__"),
        ("evaluate_evidence", "retrieve"),
        ("validate_citations", "generate"),
        ("reformulate", "extract_features"),
    } <= edges


def test_recursion_guard_is_a_structured_failure():
    from langgraph.errors import GraphRecursionError

    class BrokenGraph:
        def invoke(self, state, config):
            raise GraphRecursionError("SECRET")

    service = QueryService()
    service.app = BrokenGraph()
    response = service.execute_query(QueryRequest(query="q"))
    assert response.status == "failed"
    assert response.error == "recursion_guard"
