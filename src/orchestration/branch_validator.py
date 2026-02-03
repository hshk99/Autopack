"""
V2 Branch Validator

Validates branch names against BRANCH_NAMING_STANDARD.md.
Ensures branches follow c{CYCLE}/wave{WAVE}/{phaseId}-{description} format.
"""

import re
import json
from pathlib import Path
from typing import Optional


class BranchValidationError(ValueError):
    """Raised when a branch name fails validation."""
    
    def __init__(self, branch_name: str, reason: str):
        self.branch_name = branch_name
        self.reason = reason
        super().__init__(f"Invalid branch name '{branch_name}': {reason}")


class BranchValidator:
    """Validates branch names according to V2 naming standard."""
    
    # Standard format: c{CYCLE}/wave{WAVE}/{phaseId}-{description}
    BRANCH_PATTERN = re.compile(
        r'^c(?P<cycle>\d+)/wave(?P<wave>\d+)/(?P<phaseId>\w+)-(?P<description>[\w-]+)$'
    )
    
    # Valid phase ID prefixes (for additional validation)
    VALID_PHASE_PREFIXES = {
        'setup', 'deps', 'config', 'state', 'resource', 'webhook', 'credit',
        'glm', 'network', 'telegram', 'prompts', 'worktree', 'branch',
        'telemetry', 'orch', 'ramsafe', 'agentstate', 'prmanager', 'ciclass',
        'poller', 'router', 'webhookhealth', 'wavemetrics', 'ramrecord',
        'unresolved', 'queue', 'planning', 'humanqueue', 'test', 'scheduler',
        'thinking', 'nudgetrack', 'cianalyze', 'dashboard', 'pausemon',
        'recurring', 'archiver', 'headless', 'nudgegen', 'deepinv',
        'cascade', 'escalate', 'mainloop', 'cleanup'
    }
    
    # Valid wave numbers for V2 project
    VALID_WAVES = {1, 2, 3, 4, 5, 6}
    
    def __init__(self, current_cycle: Optional[int] = None, naming_standard_path: Optional[Path] = None):
        """Initialize branch validator.
        
        Args:
            current_cycle: Current project cycle number (e.g., 1, 2, 3)
            naming_standard_path: Path to BRANCH_NAMING_STANDARD.md file
        """
        self.current_cycle = current_cycle
        self.naming_standard_path = naming_standard_path
        
        # Try to load cycle from config if not provided
        if self.current_cycle is None:
            self.current_cycle = self._load_current_cycle()
    
    def _load_current_cycle(self) -> int:
        """Load current cycle number from V2 configuration.
        
        Returns:
            Current cycle number (defaults to 1 if not found).
        """
        try:
            # Try to load from config/v2_config.json
            config_path = Path(__file__).parent.parent.parent / "config" / "v2_config.json"
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    # Extract cycle from paths or other config
                    # For now, default to 1
                    return 1
        except Exception:
            pass
        
        # Default to cycle 1
        return 1
    
    def validate_branch_name(self, branch_name: str) -> bool:
        """Validate a branch name against the standard.
        
        Args:
            branch_name: Branch name to validate (e.g., "c1/wave2/branch001-branch-validator")
        
        Returns:
            True if branch name is valid.
        
        Raises:
            BranchValidationError: If branch name is invalid with detailed reason.
        """
        if not branch_name:
            raise BranchValidationError(branch_name, "Branch name cannot be empty")
        
        # Check pattern match
        match = self.BRANCH_PATTERN.match(branch_name)
        if not match:
            raise BranchValidationError(
                branch_name,
                "Does not match format c{CYCLE}/wave{WAVE}/{phaseId}-{description}"
            )
        
        # Extract components
        cycle = int(match.group('cycle'))
        wave = int(match.group('wave'))
        phase_id = match.group('phaseId')
        description = match.group('description')
        
        # Validate cycle
        if cycle != self.current_cycle:
            raise BranchValidationError(
                branch_name,
                f"Cycle {cycle} does not match current cycle {self.current_cycle}"
            )
        
        # Validate wave
        if wave not in self.VALID_WAVES:
            raise BranchValidationError(
                branch_name,
                f"Wave {wave} is not valid. Valid waves: {sorted(self.VALID_WAVES)}"
            )
        
        # Validate phase ID prefix
        phase_prefix = phase_id.split('0')[0]  # Extract prefix before first 0
        if phase_prefix not in self.VALID_PHASE_PREFIXES:
            raise BranchValidationError(
                branch_name,
                f"Phase ID '{phase_id}' has invalid prefix '{phase_prefix}'. "
                f"Valid prefixes: {sorted(self.VALID_PHASE_PREFIXES)}"
            )
        
        # Validate phase ID format (should be {prefix}{number})
        if not re.match(r'^\w+\d+$', phase_id):
            raise BranchValidationError(
                branch_name,
                f"Phase ID '{phase_id}' must follow format {{prefix}}{{number}} (e.g., setup001, branch001)"
            )
        
        # Validate description (should be kebab-case)
        if not re.match(r'^[\w-]+$', description):
            raise BranchValidationError(
                branch_name,
                f"Description '{description}' must be kebab-case (lowercase letters, numbers, hyphens only)"
            )
        
        # Check for uppercase letters in description
        if any(c.isupper() for c in description):
            raise BranchValidationError(
                branch_name,
                f"Description '{description}' should be lowercase (kebab-case)"
            )
        
        # Check for spaces in description
        if ' ' in description:
            raise BranchValidationError(
                branch_name,
                f"Description '{description}' should not contain spaces"
            )
        
        return True
    
    def is_valid_branch_name(self, branch_name: str) -> bool:
        """Check if a branch name is valid without raising an exception.
        
        Args:
            branch_name: Branch name to validate.
        
        Returns:
            True if valid, False otherwise.
        """
        try:
            return self.validate_branch_name(branch_name)
        except BranchValidationError:
            return False
    
    def parse_branch_name(self, branch_name: str) -> dict:
        """Parse a branch name into its components.
        
        Args:
            branch_name: Branch name to parse.
        
        Returns:
            Dictionary with keys: cycle, wave, phaseId, description
        
        Raises:
            BranchValidationError: If branch name doesn't match pattern.
        """
        match = self.BRANCH_PATTERN.match(branch_name)
        if not match:
            raise BranchValidationError(
                branch_name,
                "Cannot parse - does not match standard format"
            )
        
        return {
            'cycle': int(match.group('cycle')),
            'wave': int(match.group('wave')),
            'phaseId': match.group('phaseId'),
            'description': match.group('description'),
            'full_name': branch_name
        }
    
    def get_phase_info(self, branch_name: str) -> dict:
        """Get detailed information about a phase from its branch name.
        
        Args:
            branch_name: Branch name to analyze.
        
        Returns:
            Dictionary with phase information including wave context.
        """
        parsed = self.parse_branch_name(branch_name)
        
        # Wave context
        wave_contexts = {
            1: "Foundation & Project Setup",
            2: "Core Infrastructure",
            3: "Secondary Components & Managers",
            4: "Agent Management & Integration",
            5: "Advanced Features & Main Loop",
            6: "Final Integration & Tests"
        }
        
        return {
            **parsed,
            'wave_context': wave_contexts.get(parsed['wave'], 'Unknown'),
            'is_valid': True
        }


# Convenience function for simple validation
def validate_branch_name(branch_name: str, current_cycle: Optional[int] = None) -> bool:
    """Validate a branch name against V2 standard.
    
    This is a convenience function that creates a BranchValidator instance
    and validates the branch name.
    
    Args:
        branch_name: Branch name to validate.
        current_cycle: Current project cycle number (defaults to 1).
    
    Returns:
        True if branch name is valid.
    
    Raises:
        BranchValidationError: If branch name is invalid.
    """
    validator = BranchValidator(current_cycle=current_cycle)
    return validator.validate_branch_name(branch_name)


def is_valid_branch_name(branch_name: str, current_cycle: Optional[int] = None) -> bool:
    """Check if a branch name is valid without raising an exception.
    
    Args:
        branch_name: Branch name to check.
        current_cycle: Current project cycle number (defaults to 1).
    
    Returns:
        True if valid, False otherwise.
    """
    try:
        return validate_branch_name(branch_name, current_cycle)
    except BranchValidationError:
        return False


# CLI usage examples (for testing)
if __name__ == "__main__":
    import sys
    
    # Test branch names
    test_branches = [
        "c1/wave1/setup001-project-structure",
        "c1/wave1/deps001-requirements",
        "c1/wave1/config001-config-loader",
        "c1/wave2/state001-state-manager",
        "c1/wave2/branch001-branch-validator",
        "c1/wave3/orch001-phase-orchestrator",
        "c1/wave4/scheduler001-agent-scheduler",
        "c1/wave5/mainloop001-main-loop",
        "c2/wave1/setup001-project-structure",
        # Invalid branches
        "feature/setup-project",
        "setup001",
        "c1-wave1-setup001",
        "c1/wave1/setup001",
        "c1/wave1/setup001/project",
    ]
    
    validator = BranchValidator(current_cycle=1)
    
    print("Branch Name Validation Tests")
    print("=" * 80)
    
    for branch in test_branches:
        try:
            if validator.validate_branch_name(branch):
                info = validator.get_phase_info(branch)
                print(f"[PASS] {branch}")
                print(f"  Cycle: {info['cycle']}, Wave: {info['wave']} ({info['wave_context']})")
                print(f"  Phase: {info['phaseId']}, Description: {info['description']}")
        except BranchValidationError as e:
            print(f"[FAIL] {branch}")
            print(f"  Error: {e.reason}")
        print()
