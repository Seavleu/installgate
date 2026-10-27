// InstallGate data contracts (TypeScript, zod v3/v4). Mirror of contracts.py.
// Generate once from the Python models (pydantic -> JSON Schema -> json-schema-to-zod) in CI so the two cannot drift.
import { z } from "zod";

export const Ecosystem = z.enum(["pypi", "npm", "huggingface", "docker"]);
export const Verdict = z.enum(["ALLOW", "REVIEW", "BLOCK"]);
export const Outcome = z.enum(["ALLOW", "REVIEW", "BLOCK", "VERIFIED_SUBSTITUTE"]);
export type Verdict = z.infer<typeof Verdict>;

const rank: Record<Verdict, number> = { ALLOW: 0, REVIEW: 1, BLOCK: 2 };
export const maxVerdict = (a: Verdict, b: Verdict): Verdict => (rank[a] >= rank[b] ? a : b);

const sha256 = z.string().regex(/^[0-9a-f]{64}$/);
const evId = z.string().regex(/^EV-[0-9]{1,4}$/);

export const TargetRef = z.object({
  ecosystem: Ecosystem,
  name: z.string().min(1).max(214).regex(/^[A-Za-z0-9@/_.\-:]+$/),
  version: z.string().max(64).optional(),
  artifact_sha256: sha256.optional(),
  revision: z.string().regex(/^[0-9a-f]{40}$/).optional(),
}).strict();

export const EvidenceKind = z.enum([
  "not_found", "new_project", "new_release", "maintainer_change", "osv_malicious",
  "typosquat", "typosquat_new_project", "hf_pickle", "hf_safetensors_sibling", "runtime_below_floor",
  "web_report", "recheck_passed", "sandbox_import", "check_unavailable",
]);

export const CHECK_UNAVAILABLE_REASONS = [
  "no_floor_for_branch", "floating_tag", "digest_only", "image_not_in_table", "typosquat_unsupported_ecosystem",
] as const;

export const Evidence = z.object({
  id: evId,
  kind: EvidenceKind,
  source: z.enum(["pypi", "npm", "osv", "huggingface", "docker_registry", "policy_yaml", "tavily", "sandbox"]),
  trust: z.enum(["deterministic", "retrieved_untrusted"]),
  severity: z.enum(["info", "soft", "hard"]),
  target: TargetRef,
  observed: z.record(z.string(), z.unknown()),
  source_url: z.string().max(2048).optional(),
  fetched_at: z.string().datetime(),
  content_hash: sha256,
}).strict().refine(e => !(e.trust === "retrieved_untrusted" && e.severity === "hard"),
  { message: "untrusted (web) evidence can never be 'hard'" })
  .refine(e => !(e.kind === "check_unavailable" && e.severity === "hard"),
    { message: "check_unavailable can never be 'hard'" })
  .refine(e => e.kind !== "check_unavailable" ||
    (CHECK_UNAVAILABLE_REASONS as readonly unknown[]).includes(e.observed["reason"]),
    { message: "check_unavailable needs observed['reason'] from CHECK_UNAVAILABLE_REASONS" });

export const ExplanationSentence = z.object({
  text: z.string().min(1).max(400),
  evidence_ids: z.array(evId).min(1),
}).strict();

export const ModelTier = z.enum(["nano", "super", "ultra"]);

export const RouteCall = z.object({
  stage: z.enum(["extract", "explain", "rank_substitute", "escalate"]),
  tier: ModelTier,
  model_id: z.string(),
  prompt_tokens: z.number().int().nonnegative(),
  completion_tokens: z.number().int().nonnegative(),
  cost_usd: z.number().nonnegative(),
  latency_ms: z.number().int().nonnegative(),
  escalation_reason: z.string().optional(),
  schema_valid: z.boolean().default(true),
  retries: z.number().int().nonnegative().default(0),
}).strict();

export const RouterReceipt = z.object({
  calls: z.array(RouteCall),
  total_cost_usd: z.number().nonnegative(),
  counterfactual_all_ultra_usd: z.number().nonnegative(),
  savings_pct: z.number(),
  price_table_version: z.string(),
  tavily_calls: z.number().int().nonnegative().default(0),
  deterministic_only_ms: z.number().int().nonnegative(),
}).strict();

export const SandboxResult = z.object({
  provider: z.literal("nebius_token_factory_sandboxes"),
  sandbox_id: z.string(),
  image_digest: z.string(),
  prepare_phase_network: z.enum(["registry_only", "on"]),
  verify_phase_network: z.literal("off"),
  egress_denial_confirmed: z.boolean(),
  exit_code: z.number().int(),
  import_ok: z.boolean(),
  probe_symbols_ok: z.array(z.string()).default([]),
  duration_ms: z.number().int().nonnegative(),
}).strict();

export const SafeRemediation = z.object({
  status: z.enum(["VERIFIED_SUBSTITUTE", "NO_SAFE_SUBSTITUTE", "VERIFICATION_UNAVAILABLE", "VERIFICATION_FAILED"]),
  original: TargetRef,
  candidate: TargetRef.optional(),
  candidate_source: z.enum(["alias_map", "top_n_neighbor", "hf_sibling", "docker_patched_floor"]).optional(),
  candidate_set_ids: z.array(z.string()).default([]),
  selected_by: z.enum(["rule", "llm_rank"]).optional(),
  verification_level: z.enum(["sandbox_import", "static_registry"]).optional(),
  recheck_evidence_ids: z.array(evId).default([]),
  approved_requirement: z.string().optional(),
  sandbox: SandboxResult.optional(),
  equivalence_note: z.string().default("import-compatible only; behavioural equivalence is not guaranteed"),
}).strict().refine(r => r.status !== "VERIFIED_SUBSTITUTE" || (
  !!r.candidate?.version && !!r.candidate?.artifact_sha256 &&
  !!r.candidate_source && r.candidate_set_ids.length > 0 && r.recheck_evidence_ids.length > 0
), { message: "verified substitute must be pinned, from a closed set, and re-checked" });

export const GateVerdict = z.object({
  request_id: z.string(),
  target: TargetRef,
  policy_version: z.string(),
  policy_verdict: Verdict,
  llm_verdict: Verdict.optional(),
  final_verdict: Verdict,
  outcome: Outcome,
  risk_score: z.number().min(0).max(1),
  failed_closed: z.boolean().default(false),
  evidence: z.array(Evidence),
  explanation: z.array(ExplanationSentence).default([]),
  dropped_sentences: z.number().int().nonnegative().default(0),
  next_action: z.enum(["proceed", "use_substitute", "ask_human", "abort"]),
  remediation: SafeRemediation.optional(),
  receipt: RouterReceipt.optional(),
}).strict().superRefine((v, ctx) => {
  const bad = (message: string) => ctx.addIssue({ code: "custom", message });
  const ids = new Set(v.evidence.map(e => e.id));
  if (ids.size !== v.evidence.length) bad("duplicate evidence ids");
  if (v.explanation.some(s => s.evidence_ids.some(i => !ids.has(i)))) bad("explanation cites unknown evidence id");
  if (v.final_verdict !== maxVerdict(v.policy_verdict, v.llm_verdict ?? "ALLOW")) bad("final_verdict must equal max(policy, llm)");
  if (v.final_verdict === "BLOCK" && v.policy_verdict !== "BLOCK") bad("BLOCK must come from deterministic policy");
  if (v.policy_verdict === "BLOCK" && !v.evidence.some(e => e.severity === "hard" && e.trust === "deterministic")) bad("policy BLOCK requires hard deterministic evidence");
  if (v.failed_closed && v.final_verdict === "ALLOW") bad("fail-closed can never yield ALLOW");
  if (v.outcome === "VERIFIED_SUBSTITUTE") {
    if (v.final_verdict === "ALLOW") bad("nothing to substitute for an ALLOW");
    if (v.remediation?.status !== "VERIFIED_SUBSTITUTE") bad("VERIFIED_SUBSTITUTE outcome requires verified remediation");
    if (v.next_action !== "use_substitute") bad("next_action must be use_substitute");
  } else if (v.outcome !== v.final_verdict) bad("outcome must mirror final_verdict");
  const pinned = !!(v.target.version && v.target.artifact_sha256) ||
    (v.target.ecosystem === "huggingface" && v.target.revision !== undefined);
  if (v.outcome === "ALLOW" && !pinned) bad("ALLOW must be pinned (version + sha256, or a Hugging Face revision) (TOCTOU)");
});

export type GateVerdict = z.infer<typeof GateVerdict>;
export type Evidence = z.infer<typeof Evidence>;
export type SafeRemediation = z.infer<typeof SafeRemediation>;
export type RouterReceipt = z.infer<typeof RouterReceipt>;