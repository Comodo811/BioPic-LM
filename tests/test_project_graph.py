from biopic.models.status import NodeStatus
from biopic.pipeline.graph import ProcessingGraph
from biopic.pipeline.node import ProcessingNode


def test_downstream_invalidation_marks_only_dependents() -> None:
    graph = ProcessingGraph()
    source = ProcessingNode(operation="source")
    stack = ProcessingNode(operation="focus_stack", inputs=(source.id,))
    edit = ProcessingNode(operation="levels", inputs=(stack.id,))
    independent = ProcessingNode(operation="source")
    for node in (source, stack, edit, independent):
        graph.add_node(node)

    stale = graph.update_node_parameters(stack.id, {"radius": 7})

    assert stale == {edit.id}
    assert graph.nodes[edit.id].status is NodeStatus.STALE
    assert graph.nodes[independent.id].status is NodeStatus.COMPLETE
    assert graph.nodes[stack.id].version == 2


def test_graph_rejects_missing_inputs() -> None:
    graph = ProcessingGraph()
    node = ProcessingNode(operation="levels", inputs=("missing",))

    try:
        graph.add_node(node)
    except ValueError as exc:
        assert "Unknown input" in str(exc)
    else:
        raise AssertionError("Expected missing dependency to fail")


def test_graph_load_prunes_legacy_missing_inputs() -> None:
    graph = ProcessingGraph.from_dict(
        {
            "nodes": [
                {
                    "id": "legacy-adjustment",
                    "operation": "levels",
                    "inputs": ["missing-source"],
                    "parameters": {},
                    "version": 1,
                    "status": "complete",
                    "cache_key": "old-cache",
                    "provenance": {},
                }
            ]
        }
    )

    node = graph.nodes["legacy-adjustment"]
    assert node.inputs == ()
    assert node.status is NodeStatus.STALE
    assert node.cache_key is None
    assert node.provenance["legacy_missing_inputs_removed"] == ["missing-source"]
