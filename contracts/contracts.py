"""InstallGate data contracts (Pydantic v2).

FROZEN as of gate G1 (2026-10-26). Field names, types, and enum values below
are final. Renaming, adding, or removing any of them requires both engineers
on the PR (see contracts/README.md and AGENTS.md section 9) — the API, CLI,
and UI all read these field names and must stay in sync.

Design rules enforced in code, not in prose:
  * Evidence is frozen and content-hashed (immutable once emitted).
  * final_verdict == max(policy_verdict, llm_verdict) on the ALLOW<REVIEW<BLOCK lattice.
  * The LLM may only raise ALLOW -> REVIEW. BLOCK requires hard, deterministic evidence.
  * Every explanation sentence must cite at least one existing Evidence id.
  * VERIFIED_SUBSTITUTE is an *outcome*, never a loosened verdict: the original target stays BLOCK/REVIEW.
  * A substitute must come from a closed candidate set and be pinned (version + sha256).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

EV_ID = r"^EV-[0-9]{1,4}$"
SHA256 = r"^[0-9a-f]{64}$"


class Ecosystem(str, Enum):
    PYPI = "pypi"
    NPM = "npm"
    HUGGINGFACE = "huggingface"
    DOCKER = "docker"


class Verdict(str, Enum):
    ALLOW = "ALLOW"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"

    @property
    def rank(self) -> int:
        return {"ALLOW": 0, "REVIEW": 1, "BLOCK": 2}[self.value]


class Outcome(str, Enum):
    ALLOW = "ALLOW"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"
    VERIFIED_SUBSTITUTE = "VERIFIED_SUBSTITUTE"  # original stays blocked; a pinned alternative passed Stage 4


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class TargetRef(Frozen):
    ecosystem: Ecosystem
    name: str = Field(min_length=1, max_length=214, pattern=r"^[A-Za-z0-9@/_.\-:]+$")  # validated BEFORE any network call
    version: Optional[str] = Field(default=None, max_length=64)
    artifact_sha256: Optional[str] = Field(default=None, pattern=SHA256)


class EvidenceKind(str, Enum):
    NOT_FOUND = "not_found"
    NEW_PROJECT = "new_project"          # first upload is recent
    NEW_RELEASE = "new_release"          # latest version is recent (soft by itself)
    MAINTAINER_CHANGE = "maintainer_change"
    OSV_MALICIOUS = "osv_malicious"      # MAL-* record
    TYPOSQUAT = "typosquat"
    TYPOSQUAT_NEW_PROJECT = "typosquat_new_project"  # derived: typosquat + first upload < 7 days (rule P4, hard)
    HF_PICKLE = "hf_pickle"
    HF_SAFETENSORS_SIBLING = "hf_safetensors_sibling"
    RUNTIME_BELOW_FLOOR = "runtime_below_floor"
    WEB_REPORT = "web_report"            # Tavily; untrusted, soft only
    RECHECK_PASSED = "recheck_passed"
    SANDBOX_IMPORT = "sandbox_import"


class Evidence(Frozen):
    id: str = Field(pattern=EV_ID)
    kind: EvidenceKind
    source: Literal["pypi", "npm", "osv", "huggingface", "docker_registry", "policy_yaml", "tavily", "sandbox"]
    trust: Literal["deterministic", "retrieved_untrusted"]
    severity: Literal["info", "soft", "hard"]
    target: TargetRef
    observed: dict[str, Any] = Field(default_factory=dict)
    source_url: Optional[str] = Field(default=None, max_length=2048)
    fetched_at: datetime
    content_hash: str = Field(pattern=SHA256)

    @staticmethod
    def compute_hash(kind: str, target: TargetRef, observed: dict[str, Any], source_url: Optional[str]) -> str:
        blob = json.dumps(
            {"k": kind, "t": target.model_dump(mode="json"), "o": observed, "u": source_url},
            sort_keys=True, separators=(",", ":"), default=str,
        )
        return hashlib.sha256(blob.encode()).hexdigest()

    @model_validator(mode="after")
    def _invariants(self) -> "Evidence":
        if self.trust == "retrieved_untrusted" and self.severity == "hard":
            raise ValueError("untrusted (web) evidence can never be 'hard'")
        if self.content_hash != self.compute_hash(self.kind.value, self.target, self.observed, self.source_url):
            raise ValueError("content_hash mismatch: evidence was mutated")
        return self


class ExplanationSentence(Frozen):
    text: str = Field(min_length=1, max_length=400)
    evidence_ids: list[str] = Field(min_length=1)


# ---------- Router ----------
class ModelTier(str, Enum):
    NANO = "nano"
    SUPER = "super"
    ULTRA = "ultra"


class RouteCall(Frozen):
    stage: Literal["extract", "explain", "rank_substitute", "escalate"]
    tier: ModelTier
    model_id: str                      # resolved from GET /v1/models at startup, never hard-coded
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    cost_usd: float = Field(ge=0)
    latency_ms: int = Field(ge=0)
    escalation_reason: Optional[str] = None
    schema_valid: bool = True          # structured output parsed on first try?
    retries: int = Field(default=0, ge=0)


class RouterReceipt(Frozen):
    calls: list[RouteCall]
    total_cost_usd: float = Field(ge=0)
    counterfactual_all_ultra_usd: float = Field(ge=0)
    savings_pct: float
    price_table_version: str           # e.g. "2026-10-25 token-factory-catalog"
    tavily_calls: int = Field(default=0, ge=0)
    deterministic_only_ms: int = Field(ge=0)   # Stage 1 latency, shown to prove the LLM is not on the hot path


# ---------- Remediation ----------
class SandboxResult(Frozen):
    provider: Literal["nebius_token_factory_sandboxes"]
    sandbox_id: str
    image_digest: str
    prepare_phase_network: Literal["registry_only", "on"]
    verify_phase_network: Literal["off"]               # verification MUST run offline
    egress_denial_confirmed: bool
    exit_code: int
    import_ok: bool
    probe_symbols_ok: list[str] = Field(default_factory=list)   # AST-validated import/hasattr probes only
    duration_ms: int = Field(ge=0)


class SafeRemediation(Frozen):
    status: Literal["VERIFIED_SUBSTITUTE", "NO_SAFE_SUBSTITUTE", "VERIFICATION_UNAVAILABLE", "VERIFICATION_FAILED"]
    original: TargetRef
    candidate: Optional[TargetRef] = None
    candidate_source: Optional[Literal["alias_map", "top_n_neighbor", "hf_sibling", "docker_patched_floor"]] = None
    candidate_set_ids: list[str] = Field(default_factory=list)    # closed set the LLM ranked over, by id
    selected_by: Optional[Literal["rule", "llm_rank"]] = None
    verification_level: Optional[Literal["sandbox_import", "static_registry"]] = None
    recheck_evidence_ids: list[str] = Field(default_factory=list)
    approved_requirement: Optional[str] = None                     # e.g. "requests-oauthlib==2.0.0 --hash=sha256:..."
    sandbox: Optional[SandboxResult] = None
    equivalence_note: str = "import-compatible only; behavioural equivalence is not guaranteed"

    @model_validator(mode="after")
    def _verified_requires_proof(self) -> "SafeRemediation":
        if self.status == "VERIFIED_SUBSTITUTE":
            c = self.candidate
            if c is None or not c.version or not c.artifact_sha256:
                raise ValueError("verified substitute must be pinned (version + sha256)")
            if self.candidate_source is None or not self.candidate_set_ids:
                raise ValueError("substitute must come from a closed candidate set")
            if not self.recheck_evidence_ids:
                raise ValueError("Stage 1 must be re-run on the substitute")
            if self.verification_level == "sandbox_import":
                s = self.sandbox
                if s is None or not (s.import_ok and s.egress_denial_confirmed and s.exit_code == 0):
                    raise ValueError("sandbox verification incomplete")
            elif self.verification_level != "static_registry":
                raise ValueError("verification_level required")
        return self


# ---------- Verdict ----------
class GateVerdict(Frozen):
    request_id: str
    target: TargetRef
    policy_version: str
    policy_verdict: Verdict
    llm_verdict: Optional[Verdict] = None
    final_verdict: Verdict
    outcome: Outcome
    risk_score: float = Field(ge=0, le=1)
    failed_closed: bool = False
    evidence: list[Evidence]
    explanation: list[ExplanationSentence] = Field(default_factory=list)
    dropped_sentences: int = Field(default=0, ge=0)
    next_action: Literal["proceed", "use_substitute", "ask_human", "abort"]
    remediation: Optional[SafeRemediation] = None
    receipt: Optional[RouterReceipt] = None

    @model_validator(mode="after")
    def _invariants(self) -> "GateVerdict":
        ids = {e.id for e in self.evidence}
        if len(ids) != len(self.evidence):
            raise ValueError("duplicate evidence ids")
        for s in self.explanation:
            if not set(s.evidence_ids) <= ids:
                raise ValueError("explanation cites unknown evidence id")
        # lattice: LLM can only tighten
        llm = self.llm_verdict or Verdict.ALLOW
        expected = self.policy_verdict if self.policy_verdict.rank >= llm.rank else llm
        if self.final_verdict != expected:
            raise ValueError("final_verdict must equal max(policy, llm)")
        # LLM may raise ALLOW->REVIEW only; BLOCK needs hard deterministic evidence
        if self.final_verdict == Verdict.BLOCK and self.policy_verdict != Verdict.BLOCK:
            raise ValueError("BLOCK must come from deterministic policy, not the LLM")
        if self.policy_verdict == Verdict.BLOCK and not any(
            e.severity == "hard" and e.trust == "deterministic" for e in self.evidence
        ):
            raise ValueError("policy BLOCK requires hard deterministic evidence")
        if self.failed_closed and self.final_verdict == Verdict.ALLOW:
            raise ValueError("fail-closed can never yield ALLOW")
        # outcome consistency
        if self.outcome == Outcome.VERIFIED_SUBSTITUTE:
            if self.final_verdict == Verdict.ALLOW:
                raise ValueError("nothing to substitute for an ALLOW")
            if not self.remediation or self.remediation.status != "VERIFIED_SUBSTITUTE":
                raise ValueError("VERIFIED_SUBSTITUTE outcome requires verified remediation")
            if self.next_action != "use_substitute":
                raise ValueError("next_action must be use_substitute")
        elif self.outcome.value != self.final_verdict.value:
            raise ValueError("outcome must mirror final_verdict unless VERIFIED_SUBSTITUTE")
        if self.final_verdict == Verdict.ALLOW and self.outcome == Outcome.ALLOW and not (
            self.target.version and self.target.artifact_sha256
        ):
            raise ValueError("ALLOW must be pinned (version + sha256) to be meaningful (TOCTOU)")
        return self