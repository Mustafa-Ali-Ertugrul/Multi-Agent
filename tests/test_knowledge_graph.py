from __future__ import annotations

from pathlib import Path

from multiagent.agents.knowledge_graph import KnowledgeGraphAgent
from multiagent.context.store import ContextStore


def test_knowledge_graph_agent_builds_ast_nodes_and_edges(tmp_path: Path) -> None:
    context = ContextStore(repo_path=tmp_path)
    context.files = {
        "service.py": "\n".join(
            [
                "import json",
                "class UserService:",
                "    def save(self):",
                "        json.dumps({})",
                "def build_user():",
                "    return UserService()",
            ]
        )
    }

    KnowledgeGraphAgent().run(context)

    assert context.knowledge_graph is not None
    node_kinds = {node.kind for node in context.knowledge_graph.nodes}
    edge_kinds = {edge.kind for edge in context.knowledge_graph.edges}
    assert {"file", "module", "class", "method", "function", "import"} <= node_kinds
    assert {"defines", "imports", "contains", "calls"} <= edge_kinds
