"""Feature Gate API endpoints for IMP-REL-001.

Provides REST API for querying and managing feature gates at runtime:
- GET /features - List all features and their enabled/disabled states
- GET /features/{feature_id} - Get details about a specific feature
- GET /features/enabled - List only enabled features
- POST /features/{feature_id}/enable - Enable a feature at runtime
- POST /features/{feature_id}/disable - Disable a feature at runtime
- GET /features/validate - Validate feature gate state
"""

import logging
from typing import Dict

from fastapi import APIRouter, HTTPException

from autopack.feature_gates import (
    check_feature_dependencies,
    get_disabled_features,
    get_enabled_features,
    get_feature_info,
    get_feature_states,
    is_feature_enabled,
    reset_feature_overrides,
    set_feature_enabled,
    validate_feature_state,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/features", tags=["features"])


@router.get("")
def list_features() -> Dict[str, object]:
    """
    List all features and their enabled/disabled states.

    Returns:
        {
            "features": {
                "feature_id": {
                    "feature_id": "feature_id",
                    "name": "Feature Name",
                    "enabled": true|false,
                    "wave": "wave1",
                    "imp_id": "IMP-RES-001",
                    "risk_level": "MEDIUM",
                    "requires": ["other_feature"]
                },
                ...
            },
            "summary": {
                "total": int,
                "enabled": int,
                "disabled": int
            }
        }
    """
    states = get_feature_states()
    return {
        "features": states,
        "summary": {
            "total": len(states),
            "enabled": len(get_enabled_features()),
            "disabled": len(get_disabled_features()),
        },
    }


@router.get("/enabled")
def list_enabled_features() -> Dict[str, object]:
    """
    List only enabled features.

    Returns:
        {
            "features": {
                "feature_id": {...},
                ...
            },
            "count": int
        }
    """
    enabled = get_enabled_features()
    return {
        "features": enabled,
        "count": len(enabled),
    }


@router.get("/disabled")
def list_disabled_features() -> Dict[str, object]:
    """
    List only disabled features.

    Returns:
        {
            "features": {
                "feature_id": {...},
                ...
            },
            "count": int
        }
    """
    disabled = get_disabled_features()
    return {
        "features": disabled,
        "count": len(disabled),
    }


@router.get("/validate")
def validate_gates() -> Dict[str, object]:
    """
    Validate feature gate state and report any issues.

    Checks for:
    - Features with unmet dependencies
    - Invalid kill switch environment variable values
    - Other consistency issues

    Returns:
        {
            "valid": true|false,
            "issues": ["issue 1", "issue 2"],
            "total_features": int,
            "enabled_count": int,
            "disabled_count": int
        }
    """
    validation = validate_feature_state()
    status_code = 200 if validation["valid"] else 207  # 207 Multi-Status for warnings
    return validation


@router.get("/{feature_id}")
def get_feature(feature_id: str) -> Dict[str, object]:
    """
    Get detailed information about a specific feature.

    Args:
        feature_id: Feature identifier

    Returns:
        {
            "feature": {
                "feature_id": "feature_id",
                "name": "Feature Name",
                "enabled": true|false,
                "wave": "wave1",
                "imp_id": "IMP-RES-001",
                "risk_level": "MEDIUM",
                "description": "Feature description",
                "kill_switch_env": "AUTOPACK_ENABLE_FEATURE",
                "requires": ["dependency"]
            },
            "dependencies": {
                "status": "satisfied|missing",
                "missing_features": ["feature_id"]
            }
        }
    """
    feature_info = get_feature_info(feature_id)
    if not feature_info:
        raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found")

    deps_satisfied, missing_deps = check_feature_dependencies(feature_id)

    return {
        "feature": {
            "feature_id": feature_info.feature_id,
            "name": feature_info.name,
            "enabled": is_feature_enabled(feature_id),
            "wave": feature_info.wave,
            "imp_id": feature_info.imp_id,
            "risk_level": feature_info.risk_level,
            "description": feature_info.description,
            "kill_switch_env": feature_info.kill_switch_env,
            "requires": feature_info.requires or [],
        },
        "dependencies": {
            "status": "satisfied" if deps_satisfied else "missing",
            "missing_features": missing_deps,
        },
    }


@router.post("/{feature_id}/enable")
def enable_feature(feature_id: str) -> Dict[str, object]:
    """
    Enable a feature at runtime.

    Args:
        feature_id: Feature identifier

    Returns:
        {
            "feature_id": "feature_id",
            "enabled": true,
            "message": "Feature enabled at runtime"
        }

    Raises:
        HTTPException: 404 if feature not found
        HTTPException: 400 if dependencies not satisfied
    """
    feature_info = get_feature_info(feature_id)
    if not feature_info:
        raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found")

    # Check dependencies
    deps_satisfied, missing_deps = check_feature_dependencies(feature_id)
    if not deps_satisfied:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Feature dependencies not satisfied",
                "missing_features": missing_deps,
            },
        )

    set_feature_enabled(feature_id, True)
    logger.info(f"Feature '{feature_id}' enabled at runtime")

    return {
        "feature_id": feature_id,
        "enabled": True,
        "message": f"Feature '{feature_id}' enabled at runtime",
    }


@router.post("/{feature_id}/disable")
def disable_feature(feature_id: str) -> Dict[str, object]:
    """
    Disable a feature at runtime (emergency kill switch).

    Args:
        feature_id: Feature identifier

    Returns:
        {
            "feature_id": "feature_id",
            "enabled": false,
            "message": "Feature disabled at runtime"
        }

    Raises:
        HTTPException: 404 if feature not found
    """
    feature_info = get_feature_info(feature_id)
    if not feature_info:
        raise HTTPException(status_code=404, detail=f"Feature '{feature_id}' not found")

    set_feature_enabled(feature_id, False)
    logger.warning(f"Feature '{feature_id}' disabled at runtime (emergency kill switch)")

    return {
        "feature_id": feature_id,
        "enabled": False,
        "message": f"Feature '{feature_id}' disabled at runtime (kill switch activated)",
    }
