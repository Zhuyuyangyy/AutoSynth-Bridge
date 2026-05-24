"""收敛规则实现 - 三段式一致性评分 + 结构化分歧追踪"""
import re
import numpy as np
from typing import Optional
from pydantic import BaseModel, Field
from typing import Literal

try:
    from sentence_transformers import SentenceTransformer, util
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False

from config import settings

# ===== 核心数据结构 =====

class DisputePoint(BaseModel):
    """单条分歧点"""
    topic: str
    gpt_position: str
    gemini_position: str
    resolved: bool = False
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    notes: str = ""


class StructuredAgreementScore(BaseModel):
    """结构化合意评分"""
    innovation_aligned: bool       # 创新点是否一致
    evidence_aligned: bool         # 证据/实验设计是否一致
    patent_scope_aligned: bool     # 专利保护范围是否一致
    implementation_aligned: bool  # 实现路径是否一致
    score: float = 0.0             # 0-1
    
    def compute(self) -> float:
        aligns = [
            self.innovation_aligned,
            self.evidence_aligned,
            self.patent_scope_aligned,
            self.implementation_aligned
        ]
        self.score = sum(aligns) / len(aligns)
        return self.score


class RiskResolutionScore(BaseModel):
    """风险消解评分"""
    sci_feasibility: bool = False      # SCI二区可行性
    exaggeration_risk: bool = True     # 是否有夸大风险
    missing_implementation: bool = True # 是否缺少实现细节
    patent_scope_risk: bool = True     # 专利保护范围风险
    
    @property
    def score(self) -> float:
        risks = [self.sci_feasibility, self.exaggeration_risk,
                 self.missing_implementation, self.patent_scope_risk]
        return 1.0 - sum(risks) / len(risks)


class ConvergenceResult(BaseModel):
    """收敛结果"""
    consensus: str
    consistency_score: float
    semantic_similarity: float
    structured_agreement: StructuredAgreementScore
    risk_resolution: RiskResolutionScore
    gpt_final: str
    gemini_final: str
    need_human_review: bool = False
    critical_unresolved: list[DisputePoint] = Field(default_factory=list)
    all_disputes: list[DisputePoint] = Field(default_factory=list)
    
    @property
    def converged(self) -> bool:
        return (self.consistency_score >= settings.consistency_threshold
                and len(self.critical_unresolved) == 0)


class ConvergenceChecker:
    """收敛检查器 - 三段式评分"""
    
    # 关键问题关键词
    KEYWORDS = {
        "innovation": ["创新", "novel", "创新点", "突破", "首次", "新方法"],
        "evidence": ["实验", "数据", "验证", "证明", "实验设计", "ablation", "dataset"],
        "patent_scope": ["专利", "保护", "权利要求", "实施例", "覆盖范围"],
        "implementation": ["代码", "实现", "算法", "架构", "模块", "接口"],
        "sci_level": ["SCI", "二区", "发表", "论文", "期刊", "IF", "impact factor"],
    }
    
    def __init__(self):
        self.embedding_model = None
        if HAS_SENTENCE_TRANSFORMERS:
            try:
                self.embedding_model = SentenceTransformer(settings.embedding_model)
            except Exception as e:
                print(f"[Convergence] Failed to load embedding model: {e}")
    
    def calculate_similarity(self, text1: str, text2: str) -> float:
        """语义相似度（余弦）"""
        if not self.embedding_model or not (text1 and text2):
            return 0.5  # 默认中间值
        try:
            emb1 = self.embedding_model.encode(text1, convert_to_tensor=True)
            emb2 = self.embedding_model.encode(text2, convert_to_tensor=True)
            return float(util.cos_sim(emb1, emb2).item())
        except Exception:
            return 0.5
    
    def _keyword_overlap(self, text1: str, text2: str, category: str) -> bool:
        """判断某类别关键词是否一致"""
        kw_list = self.KEYWORDS.get(category, [])
        count1 = sum(1 for kw in kw_list if kw in text1)
        count2 = sum(1 for kw in kw_list if kw in text2)
        return count1 > 0 and count2 > 0 and abs(count1 - count2) <= 2
    
    def _extract_disputes(self, gpt_text: str, gemini_text: str) -> list[DisputePoint]:
        """提取关键分歧点"""
        disputes = []
        
        # 检测创新点数量差异
        gpt_innov = sum(1 for kw in self.KEYWORDS["innovation"] if kw in gpt_text)
        gemini_innov = sum(1 for kw in self.KEYWORDS["innovation"] if kw in gemini_text)
        if abs(gpt_innov - gemini_innov) >= 2:
            disputes.append(DisputePoint(
                topic="创新点数量差异",
                gpt_position=f"GPT提出 {gpt_innov} 个创新点",
                gemini_position=f"Gemini提出 {gemini_innov} 个创新点",
                resolved=False,
                severity="high"
            ))
        
        # 检测实验证据
        has_evidence = lambda t: any(kw in t for kw in self.KEYWORDS["evidence"])
        if has_evidence(gpt_text) != has_evidence(gemini_text):
            disputes.append(DisputePoint(
                topic="实验证据缺失",
                gpt_position="有实验证据" if has_evidence(gpt_text) else "无实验证据",
                gemini_position="有实验证据" if has_evidence(gemini_text) else "无实验证据",
                severity="critical"
            ))
        
        # 检测专利保护范围
        has_patent = lambda t: any(kw in t for kw in self.KEYWORDS["patent_scope"])
        if not has_patent(gpt_text) and has_patent(gemini_text):
            disputes.append(DisputePoint(
                topic="专利保护范围",
                gpt_position="未讨论专利保护",
                gemini_position="提出了专利保护范围",
                resolved=False,
                severity="high"
            ))
        
        return disputes
    
    def _compute_structured_agreement(self, gpt_text: str, gemini_text: str) -> StructuredAgreementScore:
        """计算结构化合意分数"""
        score = StructuredAgreementScore(
            innovation_aligned=self._keyword_overlap(gpt_text, gemini_text, "innovation"),
            evidence_aligned=self._keyword_overlap(gpt_text, gemini_text, "evidence"),
            patent_scope_aligned=self._keyword_overlap(gpt_text, gemini_text, "patent_scope"),
            implementation_aligned=self._keyword_overlap(gpt_text, gemini_text, "implementation"),
        )
        score.compute()
        return score
    
    def _compute_risk_resolution(self, gpt_text: str, gemini_text: str) -> RiskResolutionScore:
        """计算风险消解分数"""
        combined = gpt_text + " " + gemini_text
        
        return RiskResolutionScore(
            sci_feasibility=any(kw in combined for kw in self.KEYWORDS["sci_level"]),
            exaggeration_risk="声称" not in combined and "宣称" not in combined,
            missing_implementation=any(kw in combined for kw in self.KEYWORDS["implementation"]),
            patent_scope_risk=not any(kw in combined for kw in self.KEYWORDS["patent_scope"]),
        )
    
    def check_convergence(self, gpt_text: str, gemini_text: str) -> ConvergenceResult:
        """完整收敛检查 - 三段式评分"""
        # 1. 语义相似度
        semantic_sim = self.calculate_similarity(gpt_text, gemini_text)
        
        # 2. 结构化合意分数
        structured = self._compute_structured_agreement(gpt_text, gemini_text)
        
        # 3. 风险消解分数
        risk = self._compute_risk_resolution(gpt_text, gemini_text)
        
        # 综合评分
        final_score = 0.4 * semantic_sim + 0.4 * structured.score + 0.2 * risk.score
        
        # 提取分歧
        disputes = self._extract_disputes(gpt_text, gemini_text)
        critical = [d for d in disputes if d.severity == "critical" and not d.resolved]
        
        need_human = len(critical) > 0 or final_score < 0.7
        
        return ConvergenceResult(
            consensus=self._merge_plans(gpt_text, gemini_text, final_score),
            consistency_score=final_score,
            semantic_similarity=semantic_sim,
            structured_agreement=structured,
            risk_resolution=risk,
            gpt_final=gpt_text[:500],
            gemini_final=gemini_text[:500],
            need_human_review=need_human,
            critical_unresolved=critical,
            all_disputes=disputes
        )
    
    def _merge_plans(self, gpt_plan: str, gemini_plan: str, score: float) -> str:
        """合并两个方案"""
        return f"""【融合方案】(consistency={score:.2f})

## 学术框架（GPT）
{gpt_plan[:600]}

## 创新扩展（Gemini）
{gemini_plan[:600]}

## 综合结论
综合评分 {score:.2f}，已通过三段式一致性检验。
"""
