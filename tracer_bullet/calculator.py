"""Python calculator for processing extracted data

Provides safe mathematical operations on structured data with:
- Type validation
- Error handling
- Common calculations (sum, average, percentages, etc.)
"""

import logging
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CalculationResult:
    """Result of a calculation"""
    success: bool
    value: Optional[Union[int, float]] = None
    error: Optional[str] = None


class Calculator:
    """Safe calculator for structured data"""
    
    def sum(self, values: List[Union[int, float]]) -> CalculationResult:
        """Sum a list of numbers
        
        Args:
            values: List of numbers to sum
            
        Returns:
            CalculationResult with sum or error
        """
        try:
            if not values:
                return CalculationResult(success=False, error="Empty list")
            
            # Validate all values are numeric
            for v in values:
                if not isinstance(v, (int, float)):
                    return CalculationResult(
                        success=False,
                        error=f"Non-numeric value: {v} (type: {type(v).__name__})"
                    )
            
            result = sum(values)
            logger.info(f"Sum of {len(values)} values: {result}")
            return CalculationResult(success=True, value=result)
            
        except Exception as e:
            logger.error(f"Sum calculation failed: {e}")
            return CalculationResult(success=False, error=str(e))
    
    def average(self, values: List[Union[int, float]]) -> CalculationResult:
        """Calculate average of numbers
        
        Args:
            values: List of numbers
            
        Returns:
            CalculationResult with average or error
        """
        sum_result = self.sum(values)
        if not sum_result.success:
            return sum_result
        
        try:
            avg = sum_result.value / len(values)
            logger.info(f"Average of {len(values)} values: {avg}")
            return CalculationResult(success=True, value=avg)
        except Exception as e:
            logger.error(f"Average calculation failed: {e}")
            return CalculationResult(success=False, error=str(e))
    
    def percentage(self, part: Union[int, float], whole: Union[int, float]) -> CalculationResult:
        """Calculate percentage
        
        Args:
            part: Part value
            whole: Whole value
            
        Returns:
            CalculationResult with percentage or error
        """
        try:
            if not isinstance(part, (int, float)) or not isinstance(whole, (int, float)):
                return CalculationResult(
                    success=False,
                    error="Both part and whole must be numeric"
                )
            
            if whole == 0:
                return CalculationResult(
                    success=False,
                    error="Division by zero: whole cannot be 0"
                )
            
            pct = (part / whole) * 100
            logger.info(f"Percentage: {part}/{whole} = {pct}%")
            return CalculationResult(success=True, value=pct)
            
        except Exception as e:
            logger.error(f"Percentage calculation failed: {e}")
            return CalculationResult(success=False, error=str(e))
    
    def min_max(self, values: List[Union[int, float]]) -> Dict[str, CalculationResult]:
        """Find minimum and maximum values
        
        Args:
            values: List of numbers
            
        Returns:
            Dict with 'min' and 'max' CalculationResults
        """
        try:
            if not values:
                error_result = CalculationResult(success=False, error="Empty list")
                return {"min": error_result, "max": error_result}
            
            # Validate all values are numeric
            for v in values:
                if not isinstance(v, (int, float)):
                    error_result = CalculationResult(
                        success=False,
                        error=f"Non-numeric value: {v}"
                    )
                    return {"min": error_result, "max": error_result}
            
            min_val = min(values)
            max_val = max(values)
            logger.info(f"Min/Max of {len(values)} values: {min_val}/{max_val}")
            
            return {
                "min": CalculationResult(success=True, value=min_val),
                "max": CalculationResult(success=True, value=max_val)
            }
            
        except Exception as e:
            logger.error(f"Min/Max calculation failed: {e}")
            error_result = CalculationResult(success=False, error=str(e))
            return {"min": error_result, "max": error_result}
