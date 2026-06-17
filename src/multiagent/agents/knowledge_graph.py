from __future__ import annotations

import ast

from multiagent.agents.base import Agent
from multiagent.context.store import (
    ContextStore,
    KnowledgeEdge,
    KnowledgeNode,
    RepoGraph,
)


class KnowledgeGraphAgent(Agent):
    @property
    def name(self) -> str:
        return "knowledge-graph"

    def run(self, context: ContextStore) -> ContextStore:
        nodes: list[KnowledgeNode] = []
        edges: list[KnowledgeEdge] = []

        for relative_path, content in sorted(context.files.items()):
            if not relative_path.endswith(".py"):
                continue
            file_id = f"file:{relative_path}"
            module_name = relative_path.removesuffix(".py").replace("/", ".")
            module_id = f"module:{module_name}"
            nodes.append(
                KnowledgeNode(
                    id=file_id,
                    kind="file",
                    name=relative_path,
                    file=relative_path,
                    line=1,
                )
            )
            nodes.append(
                KnowledgeNode(
                    id=module_id,
                    kind="module",
                    name=module_name,
                    file=relative_path,
                    line=1,
                )
            )
            edges.append(
                KnowledgeEdge(source=file_id, target=module_id, kind="defines")
            )
            self._scan_file(relative_path, content, module_id, nodes, edges)

        context.knowledge_graph = RepoGraph(nodes=nodes, edges=edges)
        context.decisions.append(
            f"Knowledge graph: {len(nodes)} nodes, {len(edges)} edges."
        )
        return context

    def _scan_file(
        self,
        relative_path: str,
        content: str,
        module_id: str,
        nodes: list[KnowledgeNode],
        edges: list[KnowledgeEdge],
    ) -> None:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return

        imports = _imports_from_tree(tree)
        for import_name, line in imports:
            import_id = f"import:{relative_path}:{import_name}"
            nodes.append(
                KnowledgeNode(
                    id=import_id,
                    kind="import",
                    name=import_name,
                    file=relative_path,
                    line=line,
                )
            )
            edges.append(
                KnowledgeEdge(source=module_id, target=import_id, kind="imports")
            )

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                class_id = f"class:{relative_path}:{node.name}"
                nodes.append(
                    KnowledgeNode(
                        id=class_id,
                        kind="class",
                        name=node.name,
                        file=relative_path,
                        line=node.lineno,
                    )
                )
                edges.append(
                    KnowledgeEdge(source=module_id, target=class_id, kind="contains")
                )
                self._scan_class(relative_path, node, class_id, nodes, edges)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function_id = f"function:{relative_path}:{node.name}"
                nodes.append(
                    KnowledgeNode(
                        id=function_id,
                        kind="function",
                        name=node.name,
                        file=relative_path,
                        line=node.lineno,
                    )
                )
                edges.append(
                    KnowledgeEdge(source=module_id, target=function_id, kind="contains")
                )
                self._scan_calls(node, function_id, edges)

    def _scan_class(
        self,
        relative_path: str,
        class_node: ast.ClassDef,
        class_id: str,
        nodes: list[KnowledgeNode],
        edges: list[KnowledgeEdge],
    ) -> None:
        for node in class_node.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_id = f"method:{relative_path}:{class_node.name}.{node.name}"
                nodes.append(
                    KnowledgeNode(
                        id=method_id,
                        kind="method",
                        name=f"{class_node.name}.{node.name}",
                        file=relative_path,
                        line=node.lineno,
                    )
                )
                edges.append(
                    KnowledgeEdge(source=class_id, target=method_id, kind="contains")
                )
                self._scan_calls(node, method_id, edges)

    @staticmethod
    def _scan_calls(
        function_node: ast.FunctionDef | ast.AsyncFunctionDef,
        source_id: str,
        edges: list[KnowledgeEdge],
    ) -> None:
        for node in ast.walk(function_node):
            if isinstance(node, ast.Call):
                call_name = _call_name(node.func)
                if call_name:
                    edges.append(
                        KnowledgeEdge(
                            source=source_id,
                            target=f"call:{call_name}",
                            kind="calls",
                        )
                    )


def _imports_from_tree(tree: ast.Module) -> list[tuple[str, int]]:
    imports: list[tuple[str, int]] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imports.extend(
                (f"{module}.{alias.name}", node.lineno) for alias in node.names
            )
    return imports


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""
