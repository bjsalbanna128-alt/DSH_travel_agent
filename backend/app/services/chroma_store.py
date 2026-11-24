"""ChromaDB store — PersistentClient with 4 collections for semantic search."""

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from chromadb import PersistentClient
from chromadb.config import Settings as ChromaSettings

from app.config import settings
from app.services.embeddings import get_embedding_provider

logger = logging.getLogger(__name__)

COLLECTIONS = ["attractions", "hotels", "restaurants", "trip_episodes"]

_chroma_store_instance: Optional["ChromaStore"] = None


def _metadata_where(filters: dict[str, Any]) -> dict[str, Any] | None:
    if len(filters) > 1:
        return {"$and": [{field: value} for field, value in filters.items()]}
    return filters or None


class ChromaStore:
    """Persistent ChromaDB client managing 4 collections:

    - attractions: POI semantic index for attractions
    - hotels: POI semantic index for hotels
    - restaurants: POI semantic index for restaurants
    - trip_episodes: completed trip vectors for episodic memory
    """

    def __init__(self, persist_path: str | None = None):
        path = persist_path or settings.chroma_persist_path
        self._client = PersistentClient(
            path=path,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._embed = get_embedding_provider()
        self._ensure_collections()
        logger.info(f"ChromaStore initialized at {path}")

    def _ensure_collections(self):
        existing = {c.name for c in self._client.list_collections()}
        for name in COLLECTIONS:
            if name not in existing:
                self._client.create_collection(
                    name=name,
                    metadata={"hnsw:space": "cosine"},
                )
                logger.info(f"Created ChromaDB collection: {name}")

    @property
    def _attractions(self):
        return self._client.get_collection("attractions")

    @property
    def _hotels(self):
        return self._client.get_collection("hotels")

    @property
    def _restaurants(self):
        return self._client.get_collection("restaurants")

    @property
    def _episodes(self):
        return self._client.get_collection("trip_episodes")

    # ═══════════════════════════════════════════════════════════
    # Attractions
    # ═══════════════════════════════════════════════════════════

    def add_attractions(self, attractions: list[dict]) -> int:
        """Batch add attractions with embeddings. Returns count added."""
        if not attractions:
            return 0

        ids: list[str] = []
        docs: list[str] = []
        metadatas: list[dict] = []
        embeddings: list[list[float]] = []

        for a in attractions:
            aid = a.get("id") or str(uuid.uuid4())
            ids.append(aid)
            doc = f"{a.get('name', '')}。{a.get('description', '')}。标签：{'，'.join(a.get('tags', []))}"
            docs.append(doc)
            metadatas.append({
                "name": a.get("name", ""),
                "city": a.get("city", ""),
                "category": a.get("category", ""),
                "rating": float(a.get("rating", 4.0)),
                "ticket_price": float(a.get("ticket_price_cny", 0)),
                "lat": float(a.get("location", {}).get("lat", 0)),
                "lng": float(a.get("location", {}).get("lng", 0)),
                "tags": ",".join(a.get("tags", [])),
                "suitable_for": ",".join(a.get("suitable_for", [])),
            })
            embeddings.append(self._embed.embed_query(doc))

        self._attractions.add(ids=ids, documents=docs, metadatas=metadatas, embeddings=embeddings)
        logger.info(f"Added {len(ids)} attractions to ChromaDB")
        return len(ids)

    def search_attractions(
        self,
        query: str,
        city: str = "",
        category: str = "",
        k: int = 15,
    ) -> list[dict]:
        """Semantic search attractions with optional metadata filters."""
        where: dict[str, Any] = {}
        if city:
            where["city"] = city
        if category:
            where["category"] = category

        q_embed = self._embed.embed_query(query)
        results = self._attractions.query(
            query_embeddings=[q_embed],
            n_results=k,
            where=_metadata_where(where),
        )

        items: list[dict] = []
        if not results["ids"] or not results["ids"][0]:
            return items

        for i, aid in enumerate(results["ids"][0]):
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            dist = results["distances"][0][i] if results["distances"] else 1.0
            items.append({
                "id": aid,
                "name": meta.get("name", ""),
                "category": meta.get("category", ""),
                "rating": meta.get("rating", 4.0),
                "ticket_price_cny": meta.get("ticket_price", 0),
                "location": {"lat": meta.get("lat", 0), "lng": meta.get("lng", 0)},
                "tags": meta.get("tags", "").split(",") if meta.get("tags") else [],
                "suitable_for": meta.get("suitable_for", "").split(",") if meta.get("suitable_for") else [],
                "description": results["documents"][0][i] if results["documents"] else "",
                "_chroma_score": 1.0 - dist,  # cosine distance → similarity
            })

        return items

    # ═══════════════════════════════════════════════════════════
    # Hotels
    # ═══════════════════════════════════════════════════════════

    def add_hotels(self, hotels: list[dict]) -> int:
        if not hotels:
            return 0
        ids, docs, metadatas, embeddings = [], [], [], []
        for h in hotels:
            hid = h.get("id") or str(uuid.uuid4())
            ids.append(hid)
            doc = f"{h.get('name', '')}。{h.get('description', '')}。区域：{h.get('area', '')}。设施：{'，'.join(h.get('amenities', []))}"
            docs.append(doc)
            metadatas.append({
                "name": h.get("name", ""),
                "city": h.get("city", ""),
                "area": h.get("area", ""),
                "price_per_night": float(h.get("price_per_night_cny", 0)),
                "rating": float(h.get("rating", 4.0)),
                "lat": float(h.get("location", {}).get("lat", 0)),
                "lng": float(h.get("location", {}).get("lng", 0)),
            })
            embeddings.append(self._embed.embed_query(doc))
        self._hotels.add(ids=ids, documents=docs, metadatas=metadatas, embeddings=embeddings)
        return len(ids)

    def search_hotels(self, query: str, city: str = "", max_price: float = 0, k: int = 10) -> list[dict]:
        q_embed = self._embed.embed_query(query)
        where: dict[str, Any] = {}
        if city:
            where["city"] = city
        if max_price > 0:
            where["price_per_night"] = {"$lte": max_price}

        results = self._hotels.query(
            query_embeddings=[q_embed], n_results=k,
            where=_metadata_where(where),
        )
        items: list[dict] = []
        if not results["ids"] or not results["ids"][0]:
            return items
        for i, hid in enumerate(results["ids"][0]):
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            dist = results["distances"][0][i] if results["distances"] else 1.0
            items.append({
                "id": hid, "name": meta.get("name", ""),
                "area": meta.get("area", ""),
                "price_per_night_cny": meta.get("price_per_night", 0),
                "rating": meta.get("rating", 4.0),
                "location": {"lat": meta.get("lat", 0), "lng": meta.get("lng", 0)},
                "_chroma_score": 1.0 - dist,
            })
        return items

    # ═══════════════════════════════════════════════════════════
    # Restaurants
    # ═══════════════════════════════════════════════════════════

    def add_restaurants(self, restaurants: list[dict]) -> int:
        if not restaurants:
            return 0
        ids, docs, metadatas, embeddings = [], [], [], []
        for r in restaurants:
            rid = r.get("id") or str(uuid.uuid4())
            ids.append(rid)
            doc = f"{r.get('name', '')}。{r.get('description', '')}。菜系：{r.get('cuisine', '')}。区域：{r.get('area', '')}"
            docs.append(doc)
            metadatas.append({
                "name": r.get("name", ""),
                "city": r.get("city", ""),
                "cuisine": r.get("cuisine", ""),
                "area": r.get("area", ""),
                "avg_price": float(r.get("avg_price_per_person_cny", 0)),
                "rating": float(r.get("rating", 4.0)),
                "lat": float(r.get("location", {}).get("lat", 0)),
                "lng": float(r.get("location", {}).get("lng", 0)),
            })
            embeddings.append(self._embed.embed_query(doc))
        self._restaurants.add(ids=ids, documents=docs, metadatas=metadatas, embeddings=embeddings)
        return len(ids)

    def search_restaurants(
        self, query: str, city: str = "", cuisine: str = "", k: int = 10,
    ) -> list[dict]:
        q_embed = self._embed.embed_query(query)
        where: dict[str, Any] = {}
        if city:
            where["city"] = city
        if cuisine:
            where["cuisine"] = cuisine

        results = self._restaurants.query(
            query_embeddings=[q_embed], n_results=k,
            where=_metadata_where(where),
        )
        items: list[dict] = []
        if not results["ids"] or not results["ids"][0]:
            return items
        for i, rid in enumerate(results["ids"][0]):
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            dist = results["distances"][0][i] if results["distances"] else 1.0
            items.append({
                "id": rid, "name": meta.get("name", ""),
                "cuisine": meta.get("cuisine", ""),
                "area": meta.get("area", ""),
                "avg_price_per_person_cny": meta.get("avg_price", 0),
                "rating": meta.get("rating", 4.0),
                "location": {"lat": meta.get("lat", 0), "lng": meta.get("lng", 0)},
                "_chroma_score": 1.0 - dist,
            })
        return items

    # ═══════════════════════════════════════════════════════════
    # Trip Episodes (episodic memory)
    # ═══════════════════════════════════════════════════════════

    def add_trip_episode(
        self,
        trip_id: str,
        user_id: str,
        destination: str,
        duration_days: int,
        total_budget: float,
        summary: str,
        feedback_score: float = 0.0,
    ):
        """Save a completed trip as episodic memory."""
        doc = f"目的地：{destination}。{summary}"
        embedding = self._embed.embed_query(doc)
        self._episodes.add(
            ids=[trip_id],
            documents=[doc],
            metadatas=[{
                "user_id": user_id,
                "destination": destination,
                "duration_days": duration_days,
                "total_budget": total_budget,
                "feedback_score": feedback_score,
                "created_at": datetime.now().isoformat(),
            }],
            embeddings=[embedding],
        )

    def search_similar_trips(
        self,
        query: str,
        user_id: str = "",
        k: int = 3,
    ) -> list[dict]:
        """Retrieve similar past trips for context."""
        q_embed = self._embed.embed_query(query)
        where: dict[str, Any] = {}
        if user_id:
            where["user_id"] = user_id

        try:
            results = self._episodes.query(
                query_embeddings=[q_embed],
                n_results=k,
                where=where if where else None,
            )
        except Exception:
            return []

        items: list[dict] = []
        if not results["ids"] or not results["ids"][0]:
            return items
        for i, eid in enumerate(results["ids"][0]):
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            doc = results["documents"][0][i] if results["documents"] else ""
            items.append({
                "trip_id": eid,
                "destination": meta.get("destination", ""),
                "duration_days": meta.get("duration_days", 0),
                "total_budget": meta.get("total_budget", 0),
                "feedback_score": meta.get("feedback_score", 0),
                "summary": doc,
            })
        return items

    # ═══════════════════════════════════════════════════════════
    # Count / debug
    # ═══════════════════════════════════════════════════════════

    def collection_count(self, name: str) -> int:
        try:
            coll = self._client.get_collection(name)
            return coll.count()
        except Exception:
            return 0

    def delete_collection(self, name: str):
        """Delete a collection by name (used for re-seeding)."""
        try:
            self._client.delete_collection(name)
            logger.info(f"Deleted ChromaDB collection: {name}")
        except Exception as e:
            logger.warning(f"Failed to delete collection {name}: {e}")


def get_chroma_store() -> ChromaStore:
    """Get or create the singleton ChromaStore."""
    global _chroma_store_instance
    if _chroma_store_instance is None:
        _chroma_store_instance = ChromaStore()
    return _chroma_store_instance
