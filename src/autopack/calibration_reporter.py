"""Calibration Report Generator for Token Estimator.

Generates markdown reports tracking coefficient changes, confidence scores,
and calibration history for token estimation.

Features:
- Coefficient diff tracking (before/after comparisons)
- Confidence scoring based on sample size and variance
- Markdown output with tables and charts
- Historical trend analysis
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import json

logger = logging.getLogger(__name__)


@dataclass
class CoefficientChange:
    """Tracks a single coefficient change."""
    
    key: str  # e.g., "implementation/low"
    old_value: float
    new_value: float
    change_pct: float
    sample_count: int
    confidence: float
    
    @property
    def change_abs(self) -> float:
        """Absolute change in value."""
        return self.new_value - self.old_value


@dataclass
class CalibrationReport:
    """Complete calibration report."""
    
    version: str
    date: str
    sample_count: int
    changes: List[CoefficientChange] = field(default_factory=list)
    overall_confidence: float = 0.0
    notes: List[str] = field(default_factory=list)
    
    def add_change(self, change: CoefficientChange) -> None:
        """Add a coefficient change to the report."""
        self.changes.append(change)
    
    def calculate_overall_confidence(self) -> None:
        """Calculate overall confidence from individual changes."""
        if not self.changes:
            self.overall_confidence = 0.0
            return
        
        # Weight by sample count
        total_samples = sum(c.sample_count for c in self.changes)
        if total_samples == 0:
            self.overall_confidence = 0.0
            return
        
        weighted_sum = sum(
            c.confidence * c.sample_count 
            for c in self.changes
        )
        self.overall_confidence = weighted_sum / total_samples


class CalibrationReporter:
    """Generates calibration reports for token estimator."""
    
    # Confidence thresholds
    MIN_SAMPLES_HIGH_CONFIDENCE = 20
    MIN_SAMPLES_MEDIUM_CONFIDENCE = 10
    MIN_SAMPLES_LOW_CONFIDENCE = 5
    
    def __init__(self, output_dir: Optional[Path] = None):
        """Initialize reporter.
        
        Args:
            output_dir: Directory for report output (default: current dir)
        """
        self.output_dir = output_dir or Path.cwd()
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_report(
        self,
        version: str,
        old_coefficients: Dict[str, float],
        new_coefficients: Dict[str, float],
        sample_counts: Dict[str, int],
        notes: Optional[List[str]] = None
    ) -> CalibrationReport:
        """Generate calibration report.
        
        Args:
            version: Calibration version (e.g., "v5-step1")
            old_coefficients: Previous coefficient values
            new_coefficients: New coefficient values
            sample_counts: Number of samples per coefficient
            notes: Optional notes about the calibration
        
        Returns:
            CalibrationReport object
        """
        report = CalibrationReport(
            version=version,
            date=datetime.now().strftime("%Y-%m-%d"),
            sample_count=sum(sample_counts.values()),
            notes=notes or []
        )
        
        # Track changes for all coefficients
        all_keys = set(old_coefficients.keys()) | set(new_coefficients.keys())
        
        for key in sorted(all_keys):
            old_val = old_coefficients.get(key, 0.0)
            new_val = new_coefficients.get(key, 0.0)
            samples = sample_counts.get(key, 0)
            
            # Skip if no change
            if old_val == new_val:
                continue
            
            # Calculate change percentage
            if old_val != 0:
                change_pct = ((new_val - old_val) / old_val) * 100
            else:
                change_pct = 100.0 if new_val > 0 else 0.0
            
            # Calculate confidence
            confidence = self._calculate_confidence(samples, abs(change_pct))
            
            change = CoefficientChange(
                key=key,
                old_value=old_val,
                new_value=new_val,
                change_pct=change_pct,
                sample_count=samples,
                confidence=confidence
            )
            report.add_change(change)
        
        # Calculate overall confidence
        report.calculate_overall_confidence()
        
        return report
    
    def _calculate_confidence(
        self,
        sample_count: int,
        change_magnitude: float
    ) -> float:
        """Calculate confidence score for a coefficient change.
        
        Confidence is based on:
        - Sample count (more samples = higher confidence)
        - Change magnitude (larger changes need more samples)
        
        Args:
            sample_count: Number of samples
            change_magnitude: Absolute percentage change
        
        Returns:
            Confidence score (0.0 to 1.0)
        """
        # Base confidence from sample count
        if sample_count >= self.MIN_SAMPLES_HIGH_CONFIDENCE:
            base_confidence = 0.9
        elif sample_count >= self.MIN_SAMPLES_MEDIUM_CONFIDENCE:
            base_confidence = 0.7
        elif sample_count >= self.MIN_SAMPLES_LOW_CONFIDENCE:
            base_confidence = 0.5
        else:
            base_confidence = 0.3
        
        # Adjust for change magnitude
        # Large changes (>50%) need more samples for high confidence
        if change_magnitude > 50:
            magnitude_penalty = 0.2
        elif change_magnitude > 30:
            magnitude_penalty = 0.1
        else:
            magnitude_penalty = 0.0
        
        confidence = max(0.0, base_confidence - magnitude_penalty)
        return min(1.0, confidence)
    
    def to_markdown(self, report: CalibrationReport) -> str:
        """Convert report to markdown format.
        
        Args:
            report: CalibrationReport to convert
        
        Returns:
            Markdown string
        """
        lines = [
            f"# Calibration Report: {report.version}",
            "",
            f"**Date:** {report.date}  ",
            f"**Total Samples:** {report.sample_count}  ",
            f"**Overall Confidence:** {report.overall_confidence:.2%}  ",
            "",
        ]
        
        # Add notes if present
        if report.notes:
            lines.append("## Notes")
            lines.append("")
            for note in report.notes:
                lines.append(f"- {note}")
            lines.append("")
        
        # Summary statistics
        if report.changes:
            lines.append("## Summary")
            lines.append("")
            
            total_changes = len(report.changes)
            increases = sum(1 for c in report.changes if c.change_abs > 0)
            decreases = sum(1 for c in report.changes if c.change_abs < 0)
            
            lines.append(f"- **Total Changes:** {total_changes}")
            lines.append(f"- **Increases:** {increases}")
            lines.append(f"- **Decreases:** {decreases}")
            lines.append("")
            
            # Average change
            avg_change = sum(abs(c.change_pct) for c in report.changes) / total_changes
            lines.append(f"- **Average Change:** {avg_change:.1f}%")
            lines.append("")
        
        # Coefficient changes table
        if report.changes:
            lines.append("## Coefficient Changes")
            lines.append("")
            lines.append("| Coefficient | Old Value | New Value | Change | Change % | Samples | Confidence |")
            lines.append("|-------------|-----------|-----------|--------|----------|---------|------------|")
            
            for change in sorted(report.changes, key=lambda c: abs(c.change_pct), reverse=True):
                change_sign = "+" if change.change_abs > 0 else ""
                confidence_emoji = self._confidence_emoji(change.confidence)
                
                lines.append(
                    f"| `{change.key}` | {change.old_value:.0f} | {change.new_value:.0f} | "
                    f"{change_sign}{change.change_abs:.0f} | {change_sign}{change.change_pct:.1f}% | "
                    f"{change.sample_count} | {confidence_emoji} {change.confidence:.2%} |"
                )
            
            lines.append("")
        
        # Confidence breakdown
        if report.changes:
            lines.append("## Confidence Breakdown")
            lines.append("")
            
            high_conf = [c for c in report.changes if c.confidence >= 0.8]
            med_conf = [c for c in report.changes if 0.5 <= c.confidence < 0.8]
            low_conf = [c for c in report.changes if c.confidence < 0.5]
            
            lines.append(f"- **High Confidence (≥80%):** {len(high_conf)} changes")
            lines.append(f"- **Medium Confidence (50-80%):** {len(med_conf)} changes")
            lines.append(f"- **Low Confidence (<50%):** {len(low_conf)} changes")
            lines.append("")
            
            if low_conf:
                lines.append("### Low Confidence Changes (Need More Samples)")
                lines.append("")
                for change in low_conf:
                    lines.append(
                        f"- `{change.key}`: {change.sample_count} samples "
                        f"(recommend {self.MIN_SAMPLES_MEDIUM_CONFIDENCE}+ for medium confidence)"
                    )
                lines.append("")
        
        return "\n".join(lines)
    
    def _confidence_emoji(self, confidence: float) -> str:
        """Get emoji for confidence level."""
        if confidence >= 0.8:
            return "✅"
        elif confidence >= 0.5:
            return "⚠️"
        else:
            return "❌"
    
    def save_report(
        self,
        report: CalibrationReport,
        filename: Optional[str] = None
    ) -> Path:
        """Save report to markdown file.
        
        Args:
            report: CalibrationReport to save
            filename: Optional filename (default: calibration_{version}.md)
        
        Returns:
            Path to saved file
        """
        if filename is None:
            filename = f"calibration_{report.version}.md"
        
        output_path = self.output_dir / filename
        markdown = self.to_markdown(report)
        output_path.write_text(markdown, encoding="utf-8")
        
        logger.info(f"[CalibrationReporter] Saved report to {output_path}")
        return output_path
    
    def save_json(
        self,
        report: CalibrationReport,
        filename: Optional[str] = None
    ) -> Path:
        """Save report to JSON file.
        
        Args:
            report: CalibrationReport to save
            filename: Optional filename (default: calibration_{version}.json)
        
        Returns:
            Path to saved file
        """
        if filename is None:
            filename = f"calibration_{report.version}.json"
        
        output_path = self.output_dir / filename
        
        data = {
            "version": report.version,
            "date": report.date,
            "sample_count": report.sample_count,
            "overall_confidence": report.overall_confidence,
            "notes": report.notes,
            "changes": [
                {
                    "key": c.key,
                    "old_value": c.old_value,
                    "new_value": c.new_value,
                    "change_abs": c.change_abs,
                    "change_pct": c.change_pct,
                    "sample_count": c.sample_count,
                    "confidence": c.confidence
                }
                for c in report.changes
            ]
        }
        
        output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info(f"[CalibrationReporter] Saved JSON to {output_path}")
        return output_path
