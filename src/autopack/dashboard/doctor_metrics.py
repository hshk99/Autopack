"""Doctor metrics display for dashboard."""
from typing import Any, Dict, List, Optional
from dataclasses import dataclass


@dataclass
class DoctorMetrics:
    """Container for Doctor usage metrics."""
    total_calls: int = 0
    cheap_calls: int = 0
    strong_calls: int = 0
    escalations: int = 0
    actions: Dict[str, int] = None
    
    def __post_init__(self):
        if self.actions is None:
            self.actions = {}
    
    @property
    def cheap_ratio(self) -> float:
        """Calculate cheap model usage ratio."""
        if self.total_calls == 0:
            return 0.0
        return self.cheap_calls / self.total_calls
    
    @property
    def escalation_rate(self) -> float:
        """Calculate escalation frequency."""
        if self.total_calls == 0:
            return 0.0
        return self.escalations / self.total_calls
    
    def get_pie_chart_data(self) -> List[Dict[str, Any]]:
        """Get action distribution formatted for pie chart.
        
        Returns:
            List of dicts with 'name' and 'value' keys for chart rendering.
        """
        return [
            {"name": action, "value": count}
            for action, count in sorted(
                self.actions.items(),
                key=lambda x: x[1],
                reverse=True
            )
        ]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "total_calls": self.total_calls,
            "cheap_calls": self.cheap_calls,
            "strong_calls": self.strong_calls,
            "cheap_ratio": self.cheap_ratio,
            "escalations": self.escalations,
            "escalation_rate": self.escalation_rate,
            "actions": self.actions,
            "pie_chart_data": self.get_pie_chart_data()
        }


def format_doctor_stats_for_display(stats: Dict[str, Any]) -> str:
    """Format Doctor stats for terminal/log display.
    
    Args:
        stats: Dictionary from UsageRecorder.get_doctor_stats()
        
    Returns:
        Formatted string for display.
    """
    lines = [
        "=== Doctor Usage Statistics ===",
        f"Total Calls: {stats.get('total_calls', 0)}",
        f"Cheap Model Calls: {stats.get('cheap_calls', 0)}",
        f"Strong Model Calls: {stats.get('strong_calls', 0)}",
        f"Cheap Ratio: {stats.get('cheap_ratio', 0):.1%}",
        f"Escalations: {stats.get('escalations', 0)}",
        f"Escalation Rate: {stats.get('escalation_rate', 0):.1%}",
        "",
        "Action Distribution:"
    ]
    
    actions = stats.get('actions', {})
    for action, count in sorted(actions.items(), key=lambda x: x[1], reverse=True):
        lines.append(f"  {action}: {count}")
    
    return "\n".join(lines)
