import subprocess
import sys
from pathlib import Path

PYTHON = r"E:\python\Python313\python.exe"
PROJECT = str(Path(__file__).parent.parent)


def run(cmd, label):
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    result = subprocess.run(
        cmd,
        cwd=PROJECT,
        capture_output=True,
        text=True,
        shell=True
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    return result.returncode


def main():
    print("AutoSynth-Bridge Stage 3.5 Test Runner")
    print(f"Python: {PYTHON}")

    rc = 0

    rc |= run(
        f'"{PYTHON}" validate_p3.py',
        "validate_p3.py - Stage 3 standalone validation"
    )

    rc |= run(
        f'"{PYTHON}" -m pytest test_p3_debate_engine.py -v',
        "pytest test_p3_debate_engine.py"
    )

    rc |= run(
        f'"{PYTHON}" -m pytest test_debate_engine.py test_provider_contract.py test_trajectory_store.py -v',
        "pytest legacy tests (P0/P0.5)"
    )

    rc |= run(
        f'"{PYTHON}" -m pytest --ignore=test_bridge.py --tb=short -v',
        "pytest full suite (excluding test_bridge.py)"
    )

    print(f"\n{'='*60}")
    if rc == 0:
        print("ALL TEST SUITES PASSED")
    else:
        print("SOME TESTS FAILED - check output above")
    print(f"{'='*60}")
    sys.exit(rc)


if __name__ == "__main__":
    main()
