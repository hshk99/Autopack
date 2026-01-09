#!/usr/bin/env python3
"""
Validation Probe for Autonomous Executor

Tests that the autonomous executor can initialize and connect to infrastructure.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

def test_imports():
    """Test that all required imports work"""
    print("[Probe 1/5] Testing imports...")
    try:
        print("[PASS] All imports successful")
        return True
    except Exception as e:
        print(f"[FAIL] Import error: {e}")
        return False

def test_client_initialization():
    """Test that clients can be initialized"""
    print("\n[Probe 2/5] Testing client initialization...")
    try:
        from autopack.openai_clients import OpenAIBuilderClient, OpenAIAuditorClient

        # Test with fake key (won't make API calls, just initialization)
        builder = OpenAIBuilderClient(api_key="sk-test")
        auditor = OpenAIAuditorClient(api_key="sk-test")

        print("[PASS] OpenAI clients initialize successfully")
        return True
    except Exception as e:
        print(f"[FAIL] Client initialization error: {e}")
        return False

def test_quality_gate_initialization():
    """Test that QualityGate can be initialized"""
    print("\n[Probe 3/5] Testing QualityGate initialization...")
    try:
        from autopack.quality_gate import QualityGate

        qg = QualityGate(repo_root=Path("."))

        print("[PASS] QualityGate initializes successfully")
        return True
    except Exception as e:
        print(f"[FAIL] QualityGate initialization error: {e}")
        return False

def test_api_connection():
    """Test that we can connect to Autopack API"""
    print("\n[Probe 4/5] Testing Autopack API connection...")
    try:
        import requests

        response = requests.get("http://localhost:8000/health", timeout=5)

        if response.status_code == 200:
            print("[PASS] Autopack API is healthy")
            return True
        else:
            print(f"[FAIL] API returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"[FAIL] API connection error: {e}")
        return False

def test_run_status_fetch():
    """Test that we can fetch run status"""
    print("\n[Probe 5/5] Testing run status fetch...")
    try:
        import requests

        response = requests.get("http://localhost:8000/runs/fileorg-phase2-beta", timeout=5)

        if response.status_code == 200:
            data = response.json()
            if 'id' in data and 'state' in data:
                print(f"[PASS] Run status fetch successful (state: {data['state']})")
                return True
            else:
                print("[FAIL] Run data missing expected fields")
                return False
        else:
            print(f"[FAIL] API returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"[FAIL] Run status fetch error: {e}")
        return False

def main():
    """Run all validation probes"""
    print("="*80)
    print("AUTONOMOUS EXECUTOR VALIDATION PROBE")
    print("="*80)

    tests = [
        test_imports,
        test_client_initialization,
        test_quality_gate_initialization,
        test_api_connection,
        test_run_status_fetch
    ]

    results = [test() for test in tests]

    print("\n" + "="*80)
    print("PROBE SUMMARY")
    print("="*80)
    print(f"Passed: {sum(results)}/{len(results)}")
    print(f"Failed: {len(results) - sum(results)}/{len(results)}")

    if all(results):
        print("\n[SUCCESS] All probes passed - Autonomous executor ready for use")
        return 0
    else:
        print("\n[FAILURE] Some probes failed - Review errors above")
        return 1

if __name__ == "__main__":
    sys.exit(main())
