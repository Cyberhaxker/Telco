"""Lineage from the dbt manifest (dbt docs generate writes it to the shared volume)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Lineage:
    path: Path
    _mtime: float = 0.0
    _nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    _parents: dict[str, list[str]] = field(default_factory=dict)
    _children: dict[str, list[str]] = field(default_factory=dict)
    generated_at: str | None = None

    def _load(self) -> bool:
        try:
            mtime = os.path.getmtime(self.path)
        except OSError:
            return False
        if mtime == self._mtime:
            return True
        manifest = json.loads(self.path.read_text())
        nodes = {**manifest.get("nodes", {}), **manifest.get("sources", {})}
        self._nodes = {
            uid: {
                "unique_id": uid,
                "name": n.get("name"),
                "resource_type": n.get("resource_type"),
                "schema": n.get("schema"),
                "relation": f"{n.get('schema')}.{n.get('alias') or n.get('identifier') or n.get('name')}",
                "materialized": (n.get("config") or {}).get("materialized"),
                "description": n.get("description") or "",
            }
            for uid, n in nodes.items()
            if n.get("resource_type") in ("model", "seed", "snapshot", "source")
        }
        self._parents = {
            k: [p for p in v if p in self._nodes] for k, v in manifest.get("parent_map", {}).items() if k in self._nodes
        }
        self._children = {
            k: [c for c in v if c in self._nodes] for k, v in manifest.get("child_map", {}).items() if k in self._nodes
        }
        self.generated_at = manifest.get("metadata", {}).get("generated_at")
        self._mtime = mtime
        return True

    def available(self) -> bool:
        return self._load()

    def find(self, name: str) -> str | None:
        self._load()
        for uid, n in self._nodes.items():
            if name in (uid, n["name"], n["relation"]):
                return uid
        return None

    def graph(self, name: str, depth: int = 10) -> dict[str, Any] | None:
        uid = self.find(name)
        if uid is None:
            return None

        def walk(start: str, edges: dict[str, list[str]]) -> set[str]:
            seen: set[str] = set()
            frontier = {start}
            for _ in range(depth):
                frontier = {n for f in frontier for n in edges.get(f, [])} - seen
                if not frontier:
                    break
                seen |= frontier
            return seen

        up, down = walk(uid, self._parents), walk(uid, self._children)
        keep = up | down | {uid}
        edges = [{"from": p, "to": c} for c in keep for p in self._parents.get(c, []) if p in keep]
        return {
            "model": self._nodes[uid],
            "upstream": sorted(up),
            "downstream": sorted(down),
            "nodes": [self._nodes[n] for n in sorted(keep)],
            "edges": edges,
            "manifest_generated_at": self.generated_at,
        }
