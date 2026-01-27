"""Sentiment signal ingestion from community sources.

This module supports capturing community sentiment signals (Reddit, HN, blogs, etc.)
as supporting evidence for model recommendations. Sentiment is NOT the primary driver
but can nudge recommendations when combined with objective metrics.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from .models import ModelCatalog, ModelSentimentSignal


def ingest_sentiment_signal(
    session: Session,
    model_id: str,
    source: str,
    source_url: str,
    snippet: str,
    sentiment: str,
    title: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
) -> bool:
    """Ingest a single sentiment signal.

    Args:
        session: Database session.
        model_id: Model identifier.
        source: Source type (reddit, hn, twitter, blog).
        source_url: URL of the source.
        snippet: Short quote or extracted summary.
        sentiment: Sentiment label (positive, neutral, negative, mixed).
        title: Optional title of the source.
        tags: Optional tags (e.g., {"topic": "coding", "issue": "hallucination"}).

    Returns:
        True if signal was created, False if duplicate.
    """
    # Validate sentiment
    valid_sentiments = ["positive", "neutral", "negative", "mixed"]
    if sentiment not in valid_sentiments:
        raise ValueError(f"Invalid sentiment: {sentiment}. Must be one of {valid_sentiments}")

    # Ensure model exists in catalog
    catalog_entry = session.query(ModelCatalog).filter_by(model_id=model_id).first()
    if not catalog_entry:
        raise ValueError(f"Model {model_id} not found in catalog. Ingest catalog first.")

    # Check if signal already exists
    existing = (
        session.query(ModelSentimentSignal)
        .filter_by(model_id=model_id, source_url=source_url)
        .first()
    )

    if existing:
        # Update existing signal
        existing.snippet = snippet
        existing.sentiment = sentiment
        existing.title = title
        existing.tags = tags
        existing.retrieved_at = datetime.now(timezone.utc)
        session.commit()
        return False

    # Create new signal
    signal = ModelSentimentSignal(
        model_id=model_id,
        source=source,
        source_url=source_url,
        title=title,
        snippet=snippet,
        sentiment=sentiment,
        tags=tags,
    )
    session.add(signal)
    session.commit()
    return True


def ingest_sentiment_batch(
    session: Session,
    signals: List[Dict[str, any]],
) -> Dict[str, int]:
    """Ingest multiple sentiment signals in batch.

    Args:
        session: Database session.
        signals: List of signal dictionaries with keys:
            - model_id: str
            - source: str
            - source_url: str
            - snippet: str
            - sentiment: str
            - title: Optional[str]
            - tags: Optional[Dict[str, str]]

    Returns:
        Dictionary with counts: {"created": int, "updated": int}.
    """
    created = 0
    updated = 0

    for signal_data in signals:
        was_created = ingest_sentiment_signal(
            session,
            model_id=signal_data["model_id"],
            source=signal_data["source"],
            source_url=signal_data["source_url"],
            snippet=signal_data["snippet"],
            sentiment=signal_data["sentiment"],
            title=signal_data.get("title"),
            tags=signal_data.get("tags"),
        )
        if was_created:
            created += 1
        else:
            updated += 1

    return {"created": created, "updated": updated}


def get_sentiment_summary(
    session: Session,
    model_id: Optional[str] = None,
    source: Optional[str] = None,
    sentiment: Optional[str] = None,
) -> List[Dict[str, any]]:
    """Get summary of sentiment signals for reporting.

    Args:
        session: Database session.
        model_id: Filter by model (optional).
        source: Filter by source (optional).
        sentiment: Filter by sentiment (optional).

    Returns:
        List of sentiment signal dictionaries.
    """
    query = session.query(ModelSentimentSignal).order_by(ModelSentimentSignal.retrieved_at.desc())

    if model_id:
        query = query.filter(ModelSentimentSignal.model_id == model_id)
    if source:
        query = query.filter(ModelSentimentSignal.source == source)
    if sentiment:
        query = query.filter(ModelSentimentSignal.sentiment == sentiment)

    signals = query.all()

    return [
        {
            "model_id": sig.model_id,
            "source": sig.source,
            "source_url": sig.source_url,
            "title": sig.title,
            "snippet": sig.snippet,
            "sentiment": sig.sentiment,
            "tags": sig.tags,
            "retrieved_at": sig.retrieved_at.isoformat(),
        }
        for sig in signals
    ]


def compute_sentiment_score(session: Session, model_id: str) -> float:
    """Compute aggregate sentiment score for a model.

    Args:
        session: Database session.
        model_id: Model identifier.

    Returns:
        Sentiment score (0.0 to 1.0, where 1.0 is most positive).
    """
    signals = (
        session.query(ModelSentimentSignal).filter(ModelSentimentSignal.model_id == model_id).all()
    )

    if not signals:
        return 0.5  # Neutral default

    # Simple scoring: positive=1.0, mixed=0.6, neutral=0.5, negative=0.0
    sentiment_weights = {
        "positive": 1.0,
        "mixed": 0.6,
        "neutral": 0.5,
        "negative": 0.0,
    }

    total_weight = sum(sentiment_weights.get(sig.sentiment, 0.5) for sig in signals)
    avg_score = total_weight / len(signals)

    return avg_score
