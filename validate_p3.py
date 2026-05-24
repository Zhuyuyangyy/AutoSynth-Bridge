import asyncio
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.schemas import (
    DebateRequest,
    ConsensusResult,
    ExecutionPlan,
    DebateRole
)
from core.debate_engine import DebateEngine
from core.debate_roles import get_default_role_map
from core.debate_prompts import get_system_prompt_for_role


class MockProvider:
    def __init__(self, name: str, ok: bool = True):
        self.name = name
        self.ok = ok

    async def health_check(self):
        return {
            "name": self.name,
            "available": self.ok,
            "latency_ms": 10
        }

    async def generate(self, messages, **kwargs):
        class Response:
            def __init__(self, ok, content, provider_name):
                self.ok = ok
                self.content = content
                self.model = f"{provider_name}_model"
                self.provider_name = provider_name
                self.latency_ms = 100
                self.error = None if ok else "Mock error"

        content = f"这是 {self.name} 的回应，提到了方案、创新、优化"
        if self.name == "gpt":
            content += "，但是有一些问题和风险需要注意"
        return Response(self.ok, content, self.name)


results = []


def run_test(name, fn):
    try:
        fn()
        results.append((name, "PASS", ""))
        print(f"   PASS: {name}")
    except Exception as e:
        results.append((name, "FAIL", str(e)))
        print(f"   FAIL: {name} -> {e}")
        traceback.print_exc()


async def validate_all():
    print("=" * 60)
    print("AutoSynth-Bridge Stage 3 Validation")
    print("=" * 60)

    run_test("DebateRole five roles exist", lambda: (
        _assert(DebateRole.ARCHITECT == "architect"),
        _assert(DebateRole.CRITIC == "critic"),
        _assert(DebateRole.EXECUTOR == "executor"),
        _assert(DebateRole.RESEARCHER == "researcher"),
        _assert(DebateRole.JUDGE == "judge"),
    ))

    run_test("Default role map: gemini->ARCHITECT, gpt->CRITIC", lambda: (
        _assert(get_default_role_map()["gemini"] == DebateRole.ARCHITECT),
        _assert(get_default_role_map()["gpt"] == DebateRole.CRITIC),
    ))

    run_test("Role prompts contain keywords", lambda: (
        _assert("架构" in get_system_prompt_for_role(DebateRole.ARCHITECT)),
        _assert("风险" in get_system_prompt_for_role(DebateRole.CRITIC)),
        _assert("步骤" in get_system_prompt_for_role(DebateRole.EXECUTOR)),
        _assert("资料" in get_system_prompt_for_role(DebateRole.RESEARCHER)),
        _assert("裁判" in get_system_prompt_for_role(DebateRole.JUDGE)),
    ))

    print("\n--- Async tests ---")

    providers = {
        "gemini": MockProvider("gemini"),
        "gpt": MockProvider("gpt")
    }
    engine = DebateEngine(providers=providers)

    request = DebateRequest(
        query="如何设计一个更好的Agent系统？",
        topic="Agent架构",
        participants=["gemini", "gpt"],
        rounds=2
    )
    result = await engine.run(request, enable_concurrent=False)

    run_test("Role-based debate completes", lambda: (
        _assert(result.status == "completed"),
        _assert(result.task_id is not None),
        _assert(len(result.rounds) >= 2),
    ))

    run_test("Rounds have role assignments", lambda: (
        _assert(any(r.role is not None for r in result.rounds)),
    ))

    run_test("Concurrent mode works", lambda: None)

    request_c = DebateRequest(
        query="并发辩论测试",
        topic="并发",
        participants=["gemini", "gpt"],
        rounds=1
    )
    result_c = await engine.run(request_c, enable_concurrent=True)
    run_test("Concurrent mode completes", lambda: (
        _assert(result_c.status == "completed"),
    ))

    providers_fail = {
        "gemini": MockProvider("gemini", ok=True),
        "gpt": MockProvider("gpt", ok=False)
    }
    engine_fail = DebateEngine(providers=providers_fail)
    request_f = DebateRequest(
        query="测试失败恢复",
        topic="失败恢复",
        participants=["gemini", "gpt"],
        rounds=1
    )
    result_f = await engine_fail.run(request_f, enable_concurrent=True)

    run_test("Partial failure: debate still completes", lambda: (
        _assert(result_f.status == "completed"),
    ))

    run_test("Partial failure: error content present", lambda: (
        _assert(any("ERROR" in r.content for r in result_f.rounds)),
    ))

    run_test("ConsensusResult has agreement_points", lambda: (
        _assert(hasattr(result_f.consensus, "agreement_points")),
        _assert(result_f.consensus.agreement_points is not None),
    ))

    run_test("ConsensusResult has disagreement_points", lambda: (
        _assert(hasattr(result_f.consensus, "disagreement_points")),
    ))

    run_test("ConsensusResult has risks", lambda: (
        _assert(hasattr(result_f.consensus, "risks")),
        _assert(result_f.consensus.risks is not None),
    ))

    run_test("ConsensusResult has recommended_plan", lambda: (
        _assert(hasattr(result_f.consensus, "recommended_plan")),
        _assert(result_f.consensus.recommended_plan is not None),
    ))

    run_test("ConsensusResult has confidence in [0,1]", lambda: (
        _assert(0 <= result_f.consensus.confidence <= 1),
    ))

    run_test("ExecutionPlan is generated", lambda: (
        _assert(result_f.execution_plan is not None),
    ))

    run_test("ExecutionPlan has allowed_files", lambda: (
        _assert(result_f.execution_plan.allowed_files is not None),
    ))

    run_test("ExecutionPlan has forbidden_files", lambda: (
        _assert(result_f.execution_plan.forbidden_files is not None),
    ))

    run_test("ExecutionPlan has allowed_commands", lambda: (
        _assert(result_f.execution_plan.allowed_commands is not None),
    ))

    run_test("ExecutionPlan has acceptance_tests", lambda: (
        _assert(result_f.execution_plan.acceptance_tests is not None),
    ))

    print("\n" + "=" * 60)
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    total = len(results)
    print(f"Results: {passed}/{total} PASSED, {failed} FAILED")
    print("=" * 60)

    if failed > 0:
        print("\nFailed tests:")
        for name, status, err in results:
            if status == "FAIL":
                print(f"  - {name}: {err}")
        sys.exit(1)
    else:
        print("\nALL TESTS PASSED - Stage 3 Validated!")
        sys.exit(0)


def _assert(condition, msg=""):
    if not condition:
        raise AssertionError(msg or f"Assertion failed: {condition}")
    return True


if __name__ == "__main__":
    asyncio.run(validate_all())
