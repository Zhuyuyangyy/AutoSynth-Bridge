import uuid
import asyncio
from datetime import datetime
from typing import Optional, Union, List
import re

from providers.base import BaseProvider, ModelMessage
from providers.registry import ProviderRegistry
from providers.errors import ProviderNotFoundError
from core.schemas import (
    DebateRequest,
    DebateRound,
    DebateResult,
    ConsensusResult,
    ExecutionPlan,
    DebateRole
)
from core.debate_roles import get_default_role_map, DEFAULT_ROLE_CONFIGS
from core.debate_prompts import (
    get_system_prompt_for_role,
    get_debate_history_prompt,
    get_round_prompt
)


class DebateEngine:
    def __init__(self, registry_or_providers: Union[ProviderRegistry, dict, None] = None, **kwargs):
        if registry_or_providers is None:
            registry_or_providers = kwargs.get("providers", {})

        self.registry: Optional[ProviderRegistry] = None
        self._fallback_providers: dict = {}

        if isinstance(registry_or_providers, ProviderRegistry):
            self.registry = registry_or_providers
        else:
            self._fallback_providers = registry_or_providers

        self.role_map = get_default_role_map()

    def _get_provider(self, name: str) -> Optional[BaseProvider]:
        if self.registry is not None:
            if self.registry.has(name):
                return self.registry.get(name)
            return None
        if name in self._fallback_providers:
            return self._fallback_providers[name]
        return None

    def _resolve_participants(self, request: DebateRequest) -> List[tuple]:
        resolved = []
        for p in request.participants:
            if isinstance(p, dict):
                provider_name = p.get("provider", p.get("name", ""))
                role_str = p.get("role", None)
                if role_str:
                    try:
                        role = DebateRole(role_str)
                    except ValueError:
                        role = self._get_role_for_provider(provider_name)
                else:
                    role = self._get_role_for_provider(provider_name)
                resolved.append((provider_name, role))
            else:
                role = self._get_role_for_provider(p)
                resolved.append((p, role))
        return resolved

    async def run(self, request: DebateRequest, enable_concurrent: bool = True) -> DebateResult:
        task_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:4]
        result = DebateResult(
            task_id=task_id,
            query=request.query,
            topic=request.topic,
            task_type=request.task_type,
            status="running"
        )

        try:
            rounds = await self._run_debate_rounds(request, result, enable_concurrent)
            result.rounds = rounds

            consensus = self._compute_consensus(rounds, request.topic)
            result.consensus = consensus

            plan = self._build_execution_plan(request, rounds, consensus)
            result.execution_plan = plan

            result.status = "completed"
            result.completed_at = datetime.now().isoformat()

        except Exception as e:
            result.status = "error"
            result.error = str(e)
            result.completed_at = datetime.now().isoformat()

        return result

    async def _run_debate_rounds(
        self, request: DebateRequest, result: DebateResult, enable_concurrent: bool
    ) -> List[DebateRound]:
        rounds: List[DebateRound] = []
        participants = self._resolve_participants(request)

        available_participants = []
        for name, role in participants:
            provider = self._get_provider(name)
            if provider is None:
                rounds.append(DebateRound(
                    round_num=0,
                    participant=name,
                    content=f"[ERROR] Provider '{name}' not found in registry",
                    role=role.value,
                    model="",
                    provider_name=name,
                    latency_ms=0
                ))
            else:
                available_participants.append((name, role, provider))

        if len(available_participants) < 1:
            return rounds

        first_name, first_role, first_provider = available_participants[0]
        first_content = self._system_prompt_for(first_name)
        init_messages = [
            ModelMessage(role="system", content=first_content),
            ModelMessage(role="user", content=request.query)
        ]
        resp = await first_provider.generate(init_messages)
        if not resp.ok:
            rounds.append(DebateRound(
                round_num=0,
                participant=first_name,
                content=f"[ERROR] {resp.error}",
                role=first_role.value,
                model=resp.model,
                provider_name=resp.provider_name,
                latency_ms=resp.latency_ms
            ))
        else:
            rounds.append(DebateRound(
                round_num=0,
                participant=first_name,
                content=resp.content,
                role=first_role.value,
                model=resp.model,
                provider_name=resp.provider_name,
                latency_ms=resp.latency_ms
            ))

        for round_num in range(1, request.rounds + 1):
            if enable_concurrent and len(available_participants) > 1:
                round_responses = await self._concurrent_round(
                    round_num, available_participants, request.query, rounds
                )
                rounds.extend(round_responses)
            else:
                for name, role, provider in available_participants:
                    round_resp = await self._single_round(
                        round_num, name, request.query, rounds
                    )
                    rounds.append(round_resp)

        return rounds

    async def _single_round(
        self, round_num: int, participant: str, query: str, history_rounds: List[DebateRound]
    ) -> DebateRound:
        role = self._get_role_for_provider(participant)
        history = get_debate_history_prompt(history_rounds, role)
        prompt = get_round_prompt(round_num, role, query, history)
        messages = [
            ModelMessage(role="system", content=get_system_prompt_for_role(role)),
            ModelMessage(role="user", content=prompt)
        ]

        provider = self._get_provider(participant)
        if provider is None:
            return DebateRound(
                round_num=round_num,
                participant=participant,
                content=f"[ERROR] Provider '{participant}' not found",
                role=role.value,
                model="",
                provider_name=participant,
                latency_ms=0
            )

        resp = await provider.generate(messages)
        content = resp.content if resp.ok else f"[ERROR] {resp.error}"

        return DebateRound(
            round_num=round_num,
            participant=participant,
            role=role.value,
            content=content,
            model=resp.model,
            provider_name=resp.provider_name,
            latency_ms=resp.latency_ms
        )

    async def _concurrent_round(
        self, round_num: int, participants: List[tuple], query: str, history_rounds: List[DebateRound]
    ) -> List[DebateRound]:
        tasks = []
        for name, role, provider in participants:
            tasks.append(self._single_round(round_num, name, query, history_rounds))

        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        except Exception:
            results = []

        round_data = []
        for r in results:
            if isinstance(r, Exception):
                continue
            round_data.append(r)
        return round_data

    def _get_role_for_provider(self, provider_name: str) -> DebateRole:
        if provider_name in self.role_map:
            return self.role_map[provider_name]
        return DebateRole.ARCHITECT

    def _system_prompt_for(self, participant: str) -> str:
        role = self._get_role_for_provider(participant)
        return get_system_prompt_for_role(role)

    def _compute_consensus(self, rounds: List[DebateRound], topic: str) -> ConsensusResult:
        if len(rounds) < 2:
            return ConsensusResult(
                consistency_score=0.0,
                need_human_review=True,
                summary="辩论轮次不足，无法达成共识"
            )

        last_by_participant: dict = {}
        for r in rounds:
            last_by_participant[r.participant] = r

        contents = [r.content for r in last_by_participant.values()]
        overlap_score = self._keyword_overlap_score(contents)
        avg_len = sum(len(c) for c in contents) / max(1, len(contents))
        consistency_score = min(1.0, overlap_score * 0.6 + min(avg_len / 500, 1.0) * 0.4)

        converged = consistency_score >= 0.85
        need_human = not converged

        agreement_points = self._extract_agreements(contents)
        disagreement_points = self._extract_disagreements(contents)
        risks = self._extract_risks(contents)
        recommended_plan = self._extract_recommended_plan(contents)

        summary = f"关于【{topic}】的辩论共识（一致性得分: {consistency_score:.2f}）"

        return ConsensusResult(
            consistency_score=round(consistency_score, 3),
            converged=converged,
            need_human_review=need_human,
            summary=summary,
            agreement_points=agreement_points,
            disagreement_points=disagreement_points,
            risks=risks,
            recommended_plan=recommended_plan,
            confidence=consistency_score
        )

    def _keyword_overlap_score(self, contents: List[str]) -> float:
        if len(contents) < 2:
            return 0.0
        word_sets = []
        for c in contents:
            words = set(re.split(r"\W+", c.lower()))
            word_sets.append(words)
        intersection = word_sets[0]
        for s in word_sets[1:]:
            intersection = intersection & s
        union = word_sets[0]
        for s in word_sets[1:]:
            union = union | s
        return len(intersection) / max(1, len(union))

    def _extract_agreements(self, contents: List[str]) -> List[str]:
        agreements = []
        common_words = ["方案", "创新", "优化", "研究", "改进"]
        for word in common_words:
            if all(word in c for c in contents):
                agreements.append(f"各方都提到了【{word}】")
        return agreements[:5]

    def _extract_disagreements(self, contents: List[str]) -> List[str]:
        disagreements = []
        contrast_words = ["但是", "然而", "不过", "质疑", "不可行"]
        for i, c in enumerate(contents):
            for w in contrast_words:
                if w in c:
                    disagreements.append(f"参与者 {i+1} 使用了【{w}】表达不同意见")
                    break
        return disagreements[:5]

    def _extract_risks(self, contents: List[str]) -> List[str]:
        risks = []
        risk_words = ["风险", "问题", "漏洞", "难度", "挑战"]
        for c in contents:
            for w in risk_words:
                if w in c:
                    risks.append(f"提到了【{w}】")
        return list(set(risks))[:5]

    def _extract_recommended_plan(self, contents: List[str]) -> List[str]:
        steps = []
        for c in contents:
            if "步骤" in c or "方案" in c:
                steps.append(c[:300])
        return steps[:5]

    def _build_execution_plan(
        self, request: DebateRequest, rounds: List[DebateRound], consensus: ConsensusResult
    ) -> ExecutionPlan:
        last_contents = []
        seen = set()
        for r in rounds:
            if r.participant not in seen:
                last_contents.append(r.content[:300])
                seen.add(r.participant)
        summary = " | ".join(last_contents)[:500]

        return ExecutionPlan(
            title=f"{request.topic} - 执行计划",
            summary=summary,
            goal=request.query,
            steps=consensus.recommended_plan,
            constraints=consensus.risks + consensus.disagreement_points,
            allowed_files=["providers/", "core/", "memory/", "tests/"],
            forbidden_files=[".env", "data/", "browser_profiles/"],
            allowed_commands=["pytest"],
            forbidden_commands=["rm -rf", "git push --force"],
            acceptance_tests=["pytest"],
            raw_plan=summary
        )
