#!/usr/bin/env python3
"""
Semantic storage backends for tidy_workspace.

Supports:
- JSON file (fallback, no deps)
- Postgres via psycopg2 (optional, uses DATABASE_URL)
- Qdrant via qdrant-client (optional, uses QDRANT_URL/QDRANT_HOST)

Each record: {path, sha, model, decision, rationale, updated_at}
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any


class SemanticStore:
    def get(
        self, path: str, sha: str, model: str, project_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def set(self, record: Dict[str, Any], vector: Optional[list[float]] = None) -> None:
        raise NotImplementedError


class JsonSemanticStore(SemanticStore):
    def __init__(self, cache_path: Path):
        self.cache_path = cache_path
        self._data = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.cache_path.exists():
            try:
                return json.loads(self.cache_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save(self):
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    def get(
        self, path: str, sha: str, model: str, project_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        rec = self._data.get(path)
        if (
            rec
            and rec.get("sha") == sha
            and rec.get("model") == model
            and rec.get("project_id") == project_id
        ):
            return rec
        return None

    def set(self, record: Dict[str, Any], vector: Optional[list[float]] = None) -> None:
        self._data[record["path"]] = record
        self._save()


class PostgresSemanticStore(SemanticStore):
    def __init__(self, dsn: str):
        import psycopg2  # type: ignore

        self.dsn = dsn
        self.pg = psycopg2
        self._ensure_table()

    def _ensure_table(self):
        conn = self.pg.connect(self.dsn)
        cur = conn.cursor()
        cur.execute(
            """
            create table if not exists tidy_semantic_cache (
                path text primary key,
                sha text not null,
                model text not null,
                project_id text,
                decision text not null,
                rationale text,
                updated_at timestamptz not null default now()
            );
            """
        )
        cur.execute("alter table tidy_semantic_cache add column if not exists project_id text;")
        conn.commit()
        cur.close()
        conn.close()

    def get(
        self, path: str, sha: str, model: str, project_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        conn = self.pg.connect(self.dsn)
        cur = conn.cursor()
        cur.execute(
            "select path, sha, model, project_id, decision, rationale, updated_at from tidy_semantic_cache where path=%s",
            (path,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if (
            row
            and row[1] == sha
            and row[2] == model
            and (project_id is None or row[3] == project_id)
        ):
            return {
                "path": row[0],
                "sha": row[1],
                "model": row[2],
                "project_id": row[3],
                "decision": row[4],
                "rationale": row[5],
                "updated_at": row[6].isoformat() if hasattr(row[6], "isoformat") else str(row[6]),
            }
        return None

    def set(self, record: Dict[str, Any], vector: Optional[list[float]] = None) -> None:
        conn = self.pg.connect(self.dsn)
        cur = conn.cursor()
        cur.execute(
            """
            insert into tidy_semantic_cache (path, sha, model, project_id, decision, rationale, updated_at)
            values (%s, %s, %s, %s, %s, %s, %s)
            on conflict (path) do update
            set sha=excluded.sha, model=excluded.model, project_id=excluded.project_id,
                decision=excluded.decision, rationale=excluded.rationale, updated_at=excluded.updated_at
            """,
            (
                record["path"],
                record["sha"],
                record["model"],
                record.get("project_id"),
                record.get("decision"),
                record.get("rationale"),
                datetime.now(timezone.utc),
            ),
        )
        conn.commit()
        cur.close()
        conn.close()


def get_store(
    cache_path: Path, dsn_override: Optional[str], project_id: Optional[str]
) -> SemanticStore:
    dsn = dsn_override or os.getenv("DATABASE_URL")
    if dsn and dsn.startswith("postgres"):
        try:
            return PostgresSemanticStore(dsn=dsn)
        except Exception as exc:
            print(f"[WARN] Postgres store unavailable ({exc}); trying Qdrant/JSON.")
    # Qdrant
    try:
        from qdrant_client import QdrantClient  # type: ignore
    except ImportError:
        QdrantClient = None
    if QdrantClient:
        qdrant_url = os.getenv("QDRANT_URL") or os.getenv("QDRANT_HOST")
        qdrant_api_key = os.getenv("QDRANT_API_KEY")
        if qdrant_url:
            try:

                class QdrantSemanticStore(SemanticStore):
                    def __init__(self, url: str, api_key: Optional[str]):
                        self.client = QdrantClient(url=url, api_key=api_key)
                        self.collection = "tidy_semantic_cache"
                        self._ensure_collection()

                    def _ensure_collection(self):
                        from qdrant_client.http.models import Distance, VectorParams  # type: ignore

                        try:
                            self.client.get_collection(self.collection)
                        except Exception:
                            self.client.recreate_collection(
                                collection_name=self.collection,
                                vectors_config=VectorParams(size=8, distance=Distance.COSINE),
                            )

                    def _id(self, path: str, model: str, project_id: Optional[str]) -> str:
                        return f"{project_id or 'default'}::{path}::{model}"

                    def get(
                        self, path: str, sha: str, model: str, project_id: Optional[str] = None
                    ) -> Optional[Dict[str, Any]]:
                        from qdrant_client.http import models as rest  # type: ignore

                        try:
                            res = self.client.retrieve(
                                collection_name=self.collection,
                                ids=[self._id(path, model, project_id)],
                                with_payload=True,
                            )
                            if not res:
                                return None
                            payload = res[0].payload or {}
                            if (
                                payload.get("sha") == sha
                                and payload.get("project_id") == project_id
                            ):
                                return payload
                        except Exception:
                            return None
                        return None

                    def set(
                        self, record: Dict[str, Any], vector: Optional[list[float]] = None
                    ) -> None:
                        from qdrant_client.http import models as rest  # type: ignore

                        payload = record.copy()
                        vec = vector or [0.0] * 8
                        self.client.upsert(
                            collection_name=self.collection,
                            points=[
                                rest.PointStruct(
                                    id=self._id(
                                        record["path"], record["model"], record.get("project_id")
                                    ),
                                    vector=vec,
                                    payload=payload,
                                )
                            ],
                        )

                return QdrantSemanticStore(qdrant_url, qdrant_api_key)
            except Exception as exc:
                print(f"[WARN] Qdrant store unavailable ({exc}); falling back to JSON cache.")
    return JsonSemanticStore(cache_path)
