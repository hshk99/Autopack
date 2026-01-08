#!/usr/bin/env python3
"""
Enhanced file classifier with vector DB memory integration.

This module provides project-aware file classification using:
1. PostgreSQL routing rules (keyword-based)
2. Qdrant semantic similarity (vector-based)
3. Learning mechanism (stores successful classifications)
"""

import os
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timezone

# Repo root detection for dynamic paths
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

try:
    from qdrant_client import QdrantClient
    from sentence_transformers import SentenceTransformer
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False

try:
    import psycopg2
    from psycopg2 import pool
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False
    pool = None


class ProjectMemoryClassifier:
    """
    File classifier with project memory using PostgreSQL + Qdrant.

    Classification strategy:
    1. Check PostgreSQL for explicit routing rules (keyword matching)
    2. Query Qdrant for semantic similarity with past successful classifications
    3. Fall back to pattern-based classification
    4. Learn from successful classifications (store in both DBs)
    """

    def __init__(
        self,
        postgres_dsn: Optional[str] = None,
        qdrant_host: Optional[str] = None,
        qdrant_api_key: Optional[str] = None,
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        enable_learning: bool = True,
    ):
        self.postgres_dsn = postgres_dsn or os.getenv("DATABASE_URL")
        self.qdrant_host = qdrant_host or os.getenv("QDRANT_HOST", "http://localhost:6333")
        self.qdrant_api_key = qdrant_api_key or os.getenv("QDRANT_API_KEY")
        self.embedding_model_name = embedding_model
        self.enable_learning = enable_learning

        # Initialize connections
        self.pg_pool = None  # Connection pool instead of single connection
        self.pg_conn = None  # Keep for backward compatibility
        self.qdrant_client = None
        self.embedding_model = None

        self._initialize()

    def _initialize(self):
        """Initialize database connections and embedding model."""

        # PostgreSQL with connection pooling
        if self.postgres_dsn and POSTGRES_AVAILABLE and pool:
            try:
                # Create connection pool (min 1, max 5 connections)
                self.pg_pool = pool.ThreadedConnectionPool(1, 5, self.postgres_dsn)
                # Get one connection for backward compatibility
                self.pg_conn = self.pg_pool.getconn()
                # Set autocommit to avoid transaction errors
                self.pg_conn.autocommit = True
                print(f"[Classifier] OK Connected to PostgreSQL with connection pool")
            except Exception as e:
                print(f"[Classifier] WARN PostgreSQL unavailable: {e}")
                self.pg_pool = None
                self.pg_conn = None

        # Qdrant
        if QDRANT_AVAILABLE:
            try:
                if self.qdrant_api_key:
                    self.qdrant_client = QdrantClient(url=self.qdrant_host, api_key=self.qdrant_api_key)
                else:
                    self.qdrant_client = QdrantClient(url=self.qdrant_host)

                # Test connection
                self.qdrant_client.get_collections()
                print(f"[Classifier] OK Connected to Qdrant at {self.qdrant_host}")

                # Load embedding model
                self.embedding_model = SentenceTransformer(self.embedding_model_name)
                print(f"[Classifier] OK Loaded embedding model: {self.embedding_model_name}")

            except Exception as e:
                print(f"[Classifier] WARN Qdrant unavailable: {e}")
                self.qdrant_client = None

    def classify(
        self,
        file_path: Path,
        content_sample: str,
        default_project_id: str = "autopack",
    ) -> Tuple[str, str, str, float]:
        """
        Classify a file using project memory with disagreement resolution.

        Args:
            file_path: Path to the file
            content_sample: First ~500 chars of file content
            default_project_id: Default project if detection fails

        Returns:
            Tuple of (project_id, file_type, destination_path, confidence)
            confidence: 0.0-1.0, where 1.0 = very confident
        """

        filename = file_path.name.lower()
        suffix = file_path.suffix.lower()

        # Collect results from all methods
        results = {}

        # Strategy 1: PostgreSQL keyword-based rules
        pg_project, pg_type, pg_dest, pg_conf = self._classify_with_postgres(filename, content_sample, suffix)
        if pg_conf > 0.5:
            results['postgres'] = (pg_project, pg_type, pg_dest, pg_conf)

        # Strategy 2: Qdrant semantic similarity
        if self.qdrant_client and self.embedding_model:
            qd_project, qd_type, qd_dest, qd_conf = self._classify_with_qdrant(filename, content_sample, default_project_id)
            if qd_conf > 0.5:
                results['qdrant'] = (qd_project, qd_type, qd_dest, qd_conf)

        # Strategy 3: Pattern-based
        pt_project, pt_type, pt_dest, pt_conf = self._classify_with_patterns(filename, content_sample, suffix, default_project_id)
        results['pattern'] = (pt_project, pt_type, pt_dest, pt_conf)

        # Disagreement resolution: Check if methods agree
        if len(results) >= 2:
            projects = [r[0] for r in results.values()]
            types = [r[1] for r in results.values()]

            # Check for project agreement
            project_agreement = len(set(projects)) == 1
            type_agreement = len(set(types)) == 1

            if project_agreement and type_agreement:
                # Perfect agreement - boost confidence
                best_method = max(results.items(), key=lambda x: x[1][3])
                method_name, (project, file_type, dest, conf) = best_method
                boosted_conf = min(conf * 1.15, 1.0)  # Boost by 15%
                print(f"[Classifier] {method_name.upper()} (agreement boost): {project}/{file_type} (confidence={boosted_conf:.2f})")
                return project, file_type, dest, boosted_conf

            elif project_agreement and not type_agreement:
                # Project agrees but type disagrees - use highest confidence type
                project = projects[0]  # All agree on project
                best_type_result = max(results.values(), key=lambda x: x[3])
                print(f"[Classifier] Mixed (project agree, type vary): {best_type_result[0]}/{best_type_result[1]} (confidence={best_type_result[3]:.2f})")
                return best_type_result

            else:
                # Disagreement on project - use weighted voting with smart prioritization
                # Weight: postgres=2.0, qdrant=1.5, pattern=1.0
                weights = {'postgres': 2.0, 'qdrant': 1.5, 'pattern': 1.0}
                weighted_scores = {}

                for method, (proj, typ, dest, conf) in results.items():
                    key = (proj, typ)
                    score = conf * weights[method]
                    if key in weighted_scores:
                        weighted_scores[key] = (weighted_scores[key][0] + score, dest)
                    else:
                        weighted_scores[key] = (score, dest)

                # Get best weighted result
                best_key = max(weighted_scores.items(), key=lambda x: x[1][0])
                (project, file_type), (score, dest) = best_key

                # Smart prioritization: Boost confidence when high-quality signals present
                final_conf = min(score / sum(weights.values()), 1.0)

                # If PostgreSQL has high confidence (>0.8), boost final confidence
                if 'postgres' in results:
                    pg_project, pg_type, pg_dest, pg_conf = results['postgres']
                    if pg_conf >= 0.8 and pg_project == project:
                        # PostgreSQL strongly suggests this project - boost confidence
                        final_conf = max(final_conf, min(0.75, pg_conf * 0.85))
                        print(f"[Classifier] Weighted voting (PostgreSQL boost): {project}/{file_type} (confidence={final_conf:.2f})")
                        return project, file_type, dest, final_conf

                # If Qdrant has high confidence (>0.85), boost final confidence
                if 'qdrant' in results:
                    qd_project, qd_type, qd_dest, qd_conf = results['qdrant']
                    if qd_conf >= 0.85 and qd_project == project:
                        # Qdrant strongly suggests this project - boost confidence
                        final_conf = max(final_conf, min(0.70, qd_conf * 0.80))
                        print(f"[Classifier] Weighted voting (Qdrant boost): {project}/{file_type} (confidence={final_conf:.2f})")
                        return project, file_type, dest, final_conf

                # Standard weighted voting result
                print(f"[Classifier] Weighted voting: {project}/{file_type} (confidence={final_conf:.2f})")
                return project, file_type, dest, final_conf

        # Single method or no disagreement - use best available
        if results:
            best_method = max(results.items(), key=lambda x: x[1][3])
            method_name, result = best_method
            print(f"[Classifier] {method_name.upper()}: {result[0]}/{result[1]} (confidence={result[3]:.2f})")
            return result

        # Fallback
        return default_project_id, "unknown", "", 0.3

    def _classify_with_postgres(self, filename: str, content: str, suffix: str) -> Tuple[str, str, str, float]:
        """Classify using PostgreSQL routing rules (keyword matching) with user corrections priority."""

        if not self.pg_conn:
            return "", "", "", 0.0

        try:
            cursor = self.pg_conn.cursor()

            # FIRST: Check if there's a user correction for similar files (highest priority)
            try:
                cursor.execute("""
                    SELECT corrected_project, corrected_type
                    FROM classification_corrections
                    WHERE file_path ILIKE %s
                       OR file_content_sample ILIKE %s
                    LIMIT 1
                """, (f"%{filename}%", f"%{content[:100]}%"))

                correction = cursor.fetchone()
                if correction:
                    # User correction found - use it with 100% confidence
                    print(f"[Classifier] Using user correction for similar file")
                    proj, typ = correction[0], correction[1]
                    if proj == "autopack":
                        dest = str(REPO_ROOT / "archive" / f"{typ}s" / filename)
                    else:
                        dest = str(REPO_ROOT / ".autonomous_runs" / proj / "archive" / f"{typ}s" / filename)
                    cursor.close()
                    return proj, typ, dest, 1.0
            except Exception:
                # Table might not exist yet, continue with normal classification
                pass

            # SECOND: Query routing rules with keywords
            cursor.execute("""
                SELECT project_id, file_type, destination_path, content_keywords, priority
                FROM directory_routing_rules
                WHERE source_context = 'cursor' AND content_keywords IS NOT NULL
                ORDER BY priority DESC
            """)

            rows = cursor.fetchall()
            best_match = None
            best_score = 0.0

            for row in rows:
                project_id, file_type, dest_path, keywords, priority = row

                if not keywords:
                    continue

                # Score based on keyword matches in filename + content
                score = 0.0
                text = f"{filename} {content}".lower()

                for keyword in keywords:
                    if keyword.lower() in text:
                        score += 1.0 / len(keywords)  # Normalize by keyword count

                # Boost by priority
                score *= (1.0 + priority * 0.1)

                if score > best_score:
                    best_score = score
                    best_match = (project_id, file_type, dest_path)

            cursor.close()

            if best_match and best_score > 0.5:
                return best_match[0], best_match[1], best_match[2], min(best_score, 1.0)

        except Exception as e:
            print(f"[Classifier] PostgreSQL error: {e}")

        return "", "", "", 0.0

    def _classify_with_qdrant(self, filename: str, content: str, default_project: str) -> Tuple[str, str, str, float]:
        """Classify using Qdrant semantic similarity."""

        if not self.qdrant_client or not self.embedding_model:
            return "", "", "", 0.0

        try:
            # Create embedding for query
            text_to_embed = f"{filename}\n\n{content}"
            query_vector = self.embedding_model.encode(text_to_embed, normalize_embeddings=True).tolist()

            # Search for similar patterns
            results = self.qdrant_client.query_points(
                collection_name="file_routing_patterns",
                query=query_vector,
                limit=3,
                score_threshold=0.6,
            ).points

            if not results:
                return "", "", "", 0.0

            # Get best match
            best_result = results[0]
            payload = best_result.payload
            confidence = best_result.score

            return (
                payload.get("project_id", default_project),
                payload.get("file_type", "unknown"),
                payload.get("destination_path", ""),
                confidence
            )

        except Exception as e:
            print(f"[Classifier] Qdrant error: {e}")

        return "", "", "", 0.0

    def _classify_with_patterns(self, filename: str, content: str, suffix: str, default_project: str) -> Tuple[str, str, str, float]:
        """Fallback pattern-based classification with enhanced multi-signal detection."""

        # Multi-signal project detection with signal strength
        project_signals = []
        signal_strengths = []  # Track how strong each signal is
        confidence = 0.60  # Base confidence (improved from 0.55)

        # Signal 1: Filename indicators (weighted by specificity)
        if any(indicator in filename for indicator in ["fileorg", "file-org", "file_org", "file_organizer"]):
            project_signals.append("file-organizer-app-v1")
            signal_strengths.append(0.9)  # Very specific
        elif any(indicator in filename for indicator in ["backlog", "maintenance", "country_pack"]):
            project_signals.append("file-organizer-app-v1")
            signal_strengths.append(0.7)  # Moderately specific
        elif any(indicator in filename for indicator in ["autopack", "tidy", "autonomous", "executor"]):
            project_signals.append("autopack")
            signal_strengths.append(0.9)  # Very specific

        # Signal 2: Content indicators (with strength weighting)
        if content:
            content_lower = content.lower()

            # File Organizer indicators (high specificity)
            fo_high_spec = ["file organizer country pack", "uk folder structure", "canada tax documents"]
            fo_med_spec = ["file organizer", "fileorg", "country pack", "uk folder", "canada folder",
                          "australia folder", "tax document", "folder structure"]

            if any(ind in content_lower for ind in fo_high_spec):
                project_signals.append("file-organizer-app-v1")
                signal_strengths.append(0.95)  # Very high specificity
            elif any(ind in content_lower for ind in fo_med_spec):
                project_signals.append("file-organizer-app-v1")
                signal_strengths.append(0.75)  # Medium-high specificity

            # Autopack indicators (high specificity)
            ap_high_spec = ["autopack autonomous executor", "tidy workspace classification", "memory-based classification"]
            ap_med_spec = ["autopack", "autonomous executor", "tidy workspace", "run layout",
                          "phase execution", "llm usage", "context window", "qdrant vector"]

            if any(ind in content_lower for ind in ap_high_spec):
                project_signals.append("autopack")
                signal_strengths.append(0.95)  # Very high specificity
            elif any(ind in content_lower for ind in ap_med_spec):
                project_signals.append("autopack")
                signal_strengths.append(0.75)  # Medium-high specificity

        # Signal 3: File extension patterns (project-specific file types with strength)
        if suffix in [".log", ".json"] and "api_" in filename:
            project_signals.append("autopack")  # API logs typically autopack
            signal_strengths.append(0.8)  # Good indicator
        elif suffix == ".py" and ("create_fileorg" in filename or "fileorg_" in filename):
            project_signals.append("file-organizer-app-v1")
            signal_strengths.append(0.85)  # Strong indicator
        elif suffix == ".py" and ("tidy" in filename or "autonomous" in filename or "executor" in filename):
            project_signals.append("autopack")
            signal_strengths.append(0.85)  # Strong indicator

        # Determine project from signals with weighted voting
        if project_signals:
            from collections import defaultdict
            weighted_votes = defaultdict(float)

            # Sum weighted votes for each project
            for proj, strength in zip(project_signals, signal_strengths):
                weighted_votes[proj] += strength

            # Get project with highest weighted vote
            project_id = max(weighted_votes.items(), key=lambda x: x[1])[0]
            total_weight = weighted_votes[project_id]
            num_signals = len([p for p in project_signals if p == project_id])

            # Calculate confidence based on total weight and number of agreeing signals
            if total_weight >= 2.5:  # Very strong multi-signal agreement
                confidence = min(0.88, 0.60 + (total_weight * 0.11))
            elif total_weight >= 1.8:  # Strong agreement
                confidence = min(0.78, 0.60 + (total_weight * 0.10))
            elif total_weight >= 0.9:  # Moderate agreement
                confidence = min(0.70, 0.60 + (total_weight * 0.08))
            else:  # Weak signal
                confidence = 0.62  # Slightly higher than base
        else:
            project_id = default_project

        # Extension-specific type classification with content validation
        file_type = "unknown"
        type_confidence_boost = 1.0  # Multiplier for confidence

        if suffix == ".md":
            # Markdown files - check filename first, then content
            if "implementation_plan" in filename or "plan_" in filename or "_plan" in filename:
                file_type = "plan"
                type_confidence_boost = 1.2 if "## goal" in content or "## approach" in content else 1.0
            elif "analysis" in filename or "review" in filename or "revision" in filename:
                file_type = "analysis"
                type_confidence_boost = 1.2 if "## findings" in content or "## issue" in content else 1.0
            elif "report" in filename or "summary" in filename or "consolidated" in filename:
                file_type = "report"
                type_confidence_boost = 1.2 if "## summary" in content or "progress" in content else 1.0
            elif "prompt" in filename or "delegation" in filename:
                file_type = "prompt"
                type_confidence_boost = 1.2 if "## task" in content or "please" in content else 1.0
            elif "diagnostic" in filename:
                file_type = "diagnostic"
                type_confidence_boost = 1.2 if "error" in content or "trace" in content else 1.0
            # Content-based fallback for .md
            elif content:
                if "# implementation plan" in content or "## goal" in content:
                    file_type = "plan"
                elif "# analysis" in content or "## findings" in content:
                    file_type = "analysis"
                elif "# report" in content or "## summary" in content:
                    file_type = "report"

        elif suffix == ".log":
            file_type = "log"
            type_confidence_boost = 1.3  # Logs are very reliable by extension

        elif suffix == ".py":
            file_type = "script"
            type_confidence_boost = 1.1
            # Could sub-classify scripts here if needed

        elif suffix == ".json":
            # JSON files - need more context
            if "plan" in filename or "phase" in filename or "config" in filename:
                file_type = "plan"
                type_confidence_boost = 1.1
            elif "failure" in filename or "error" in filename or "diagnostic" in filename:
                file_type = "log"
                type_confidence_boost = 1.2
            else:
                file_type = "unknown"

        elif suffix in [".sql", ".sh", ".ps1"]:
            file_type = "script"
            type_confidence_boost = 1.2

        elif suffix in [".yaml", ".yml", ".toml"]:
            if "config" in filename or "settings" in filename:
                file_type = "unknown"  # Config files don't get archived
                confidence *= 0.5  # Lower confidence to avoid moving
            else:
                file_type = "plan"
                type_confidence_boost = 1.0

        # Apply type confidence boost
        confidence *= type_confidence_boost

        # ENHANCEMENT: Content validation scoring for higher confidence
        validation_boost = 0.0
        content_lower = content.lower() if content else ""

        if file_type == "plan" and content:
            # Plan-specific validation markers
            if "## goal" in content_lower: validation_boost += 0.04
            if "## approach" in content_lower: validation_boost += 0.04
            if "## implementation" in content_lower: validation_boost += 0.03
            if any(word in content_lower for word in ["milestone", "deliverable", "timeline", "phase"]):
                validation_boost += 0.03

        elif file_type == "analysis" and content:
            # Analysis-specific validation markers
            if "## findings" in content_lower: validation_boost += 0.04
            if "## issues" in content_lower or "## problems" in content_lower: validation_boost += 0.04
            if "## recommendations" in content_lower: validation_boost += 0.03
            if any(word in content_lower for word in ["performance", "bottleneck", "investigation", "root cause"]):
                validation_boost += 0.03

        elif file_type == "report" and content:
            # Report-specific validation markers
            if "## summary" in content_lower: validation_boost += 0.04
            if "## results" in content_lower: validation_boost += 0.04
            if "## conclusion" in content_lower: validation_boost += 0.03
            if any(word in content_lower for word in ["progress", "status", "metrics", "kpi"]):
                validation_boost += 0.03

        elif file_type == "script" and content:
            # Script-specific validation markers
            if any(marker in content_lower for marker in ["import ", "def ", "class ", "function"]):
                validation_boost += 0.04
            if any(marker in content_lower for marker in ["if __name__", "main()", "argparse"]):
                validation_boost += 0.03

        elif file_type == "log" and content:
            # Log-specific validation markers
            if any(marker in content_lower for marker in ["[info]", "[debug]", "[error]", "[warn]"]):
                validation_boost += 0.04
            if any(marker in content_lower for marker in ["timestamp", "datetime", "2025-", "2024-"]):
                validation_boost += 0.03

        # ENHANCEMENT: File structure heuristics
        structure_boost = 0.0
        if content:
            content_length = len(content)
            header_count = content.count("##")
            section_count = content.count("\n\n")

            # Longer files with structure = higher confidence
            if content_length > 500:
                if header_count >= 3 and section_count >= 4:
                    structure_boost = 0.04  # Well-structured document
                elif header_count >= 2 and section_count >= 2:
                    structure_boost = 0.02  # Moderately structured
                elif content_length > 1000:
                    structure_boost = 0.01  # Long but less structured
            elif content_length > 200:
                if header_count >= 2:
                    structure_boost = 0.02  # Short but structured

        # Apply validation and structure boosts
        total_boost = validation_boost + structure_boost
        if total_boost > 0:
            confidence = min(0.92, confidence + total_boost)

        # Build destination path
        if project_id == "autopack":
            if file_type == "script":
                dest = str(REPO_ROOT / "scripts" / "utility" / Path(filename).name)
            elif file_type == "unknown":
                dest = str(REPO_ROOT / "archive" / "unsorted" / Path(filename).name)
            else:
                dest = str(REPO_ROOT / "archive" / f"{file_type}s" / Path(filename).name)
        else:
            dest = str(REPO_ROOT / ".autonomous_runs" / project_id / "archive" / f"{file_type}s" / Path(filename).name)

        return project_id, file_type, dest, confidence

    def learn(
        self,
        file_path: Path,
        content_sample: str,
        project_id: str,
        file_type: str,
        destination_path: str,
        confidence: float,
    ):
        """
        Store successful classification for future learning.

        This adds the classification to:
        1. Qdrant (as a new pattern for semantic matching)
        2. PostgreSQL learning table (for analytics and refinement)
        """

        if not self.enable_learning:
            return

        try:
            # Store in Qdrant as a new pattern
            if self.qdrant_client and self.embedding_model:
                text_to_embed = f"{file_path.name}\n\n{content_sample}"
                vector = self.embedding_model.encode(text_to_embed, normalize_embeddings=True).tolist()

                # Create point ID from file hash
                file_hash = hashlib.sha256(text_to_embed.encode()).hexdigest()[:16]
                point_id = int(file_hash, 16) % (2**63)  # Convert to int for Qdrant

                from qdrant_client.http.models import PointStruct

                self.qdrant_client.upsert(
                    collection_name="file_routing_patterns",
                    points=[
                        PointStruct(
                            id=point_id,
                            vector=vector,
                            payload={
                                "project_id": project_id,
                                "file_type": file_type,
                                "example_filename": file_path.name,
                                "example_content": content_sample[:500],
                                "destination_path": destination_path,
                                "source_context": "learned",
                                "confidence": confidence,
                                "learned_at": datetime.now(timezone.utc).isoformat(),
                            }
                        )
                    ]
                )

                print(f"[Classifier] OK Learned pattern: {project_id}/{file_type}")

            # TODO: Could also store in PostgreSQL learning table for analytics

        except Exception as e:
            print(f"[Classifier] WARN Learning failed: {e}")

    def close(self):
        """Close database connections."""
        if self.pg_conn and self.pg_pool:
            # Return connection to pool and close pool
            self.pg_pool.putconn(self.pg_conn)
            self.pg_pool.closeall()
        elif self.pg_conn:
            # Legacy: close single connection if no pool
            self.pg_conn.close()


# Convenience function for integration with existing code
def classify_file_with_memory(
    file_path: Path,
    content_sample: str,
    default_project_id: str = "autopack",
    enable_learning: bool = True,
) -> Tuple[str, str, Path, float]:
    """
    Classify file using project memory.

    Returns:
        Tuple of (project_id, file_type, destination_path, confidence)
    """

    classifier = ProjectMemoryClassifier(enable_learning=enable_learning)

    project_id, file_type, dest_str, confidence = classifier.classify(
        file_path, content_sample, default_project_id
    )

    dest_path = Path(dest_str) if dest_str else None

    # Learn from high-confidence classifications
    if enable_learning and confidence > 0.8 and dest_path:
        classifier.learn(file_path, content_sample, project_id, file_type, dest_str, confidence)

    classifier.close()

    return project_id, file_type, dest_path, confidence
