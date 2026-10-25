# InstallGate architecture (UML, Mermaid)

These diagrams are the text versions of the ones in the product spec. GitHub, Cursor's Markdown preview and most editors render Mermaid directly. Edit them here; they are the source of truth for the repo.

## 1. Use case diagram

Mermaid has no native use case diagram, so this uses a flowchart with UML conventions: actors on the outside, use cases (rounded) inside the system boundary.

```mermaid
flowchart LR
  agent([Coding agent])
  dev([Developer])
  sec([Security engineer])
  ext[["«system» Token Factory, registries, OSV, Tavily"]]

  subgraph IG[InstallGate]
    uc1(Check install target)
    uc2(Propose safe substitute)
    uc3(Review cited evidence)
    uc4(Confirm or decline diff)
    uc5(Tune policy rules)
  end

  agent --- uc1
  uc1 --- ext
  uc2 -. "«extend» [BLOCK or REVIEW]" .-> uc1
  dev --- uc3
  dev --- uc4
  sec --- uc3
  sec --- uc5
```

## 2. Component view

```mermaid
flowchart TB
  entry["Entry points: CLI, HTTP API, MCP check_install"]
  subgraph svc[Public service: reads metadata, executes no package code]
    engine["1. Deterministic engine<br/>parsers, PyPI/npm, OSV, HF, Dockerfile floor<br/>emits Evidence EV-n + policy verdict"]
    router["2. Router and grounding<br/>Nano extract, Super explain, Ultra on REVIEW >= 0.6"]
    validator["3. Validator floor<br/>drop uncited sentences, stricter-of, fail closed"]
    allow["ALLOW: proceed"]
    block["BLOCK or REVIEW: closed candidate set, pin, re-check, show diff"]
  end
  human["Human or agent confirms<br/>(InstallGate never runs the command)"]
  meta[("PyPI, npm, OSV.dev, Hugging Face Hub")]
  tf[["Nebius Token Factory: Nano, Super, Ultra"]]
  tav[["Tavily search"]]

  entry --> engine --> router --> validator
  validator --> allow
  validator --> block --> human
  meta --> engine
  router --> tf
  router --> tav
```

## 3. Sequence diagram: a blocked install

```mermaid
sequenceDiagram
  autonumber
  participant A as Agent
  participant API as Gate API
  participant E as Engine
  participant R as Registries
  participant RT as Router
  participant T as Tavily
  participant N as Nemotron
  participant V as Validator

  A->>API: check_install
  API->>E: check(target)
  E->>R: metadata, OSV
  R-->>E: facts
  E-->>API: EV-n, BLOCK
  opt not a clean ALLOW
    API->>RT: explain(evidence)
    RT->>T: search
    T-->>RT: untrusted EV
    RT->>N: Nano, then Super
    N-->>RT: cited text
    RT-->>API: draft, model verdict
    API->>V: validate(draft, policy)
    V-->>API: final = stricter of the two
    API->>E: re-check candidate
    E-->>API: pinned substitute
  end
  API-->>A: verdict + diff
  Note over A,API: The agent asks a human to confirm. InstallGate never runs the command.
```

## 4. State machine

```mermaid
stateDiagram-v2
  [*] --> Checking
  state Checking {
    [*] --> Received
    Received --> Parsed
    Parsed --> Evidenced
    Evidenced --> PolicySet
    state choice1 <<choice>>
    PolicySet --> choice1
    choice1 --> Enriched: [otherwise]
    Enriched --> Validated
  }
  choice1 --> AllowFinal: [clean ALLOW]
  AllowFinal --> [*]
  Checking --> FailedClosed: error
  FailedClosed --> [*]: verdict = REVIEW
  state "REVIEW or BLOCK fixed" as Fixed
  Validated --> Fixed
  state choice2 <<choice>>
  Fixed --> choice2
  choice2 --> SubstituteProposed: [candidate passes re-check]
  choice2 --> NoSubstitute: [no safe candidate]
  NoSubstitute --> [*]: ask a human
  SubstituteProposed --> AwaitingConfirmation: diff shown
  AwaitingConfirmation --> [*]: confirmed or declined
```

## 5. Class diagram: data contracts

Key attributes only. The full definitions, with validators, are in `contracts/contracts.py`.

```mermaid
classDiagram
  class GateVerdict {
    request_id: str
    target: TargetRef
    policy_verdict: Verdict
    llm_verdict: Verdict [0..1]
    final_verdict: Verdict
    outcome: Outcome
    risk_score: float
    failed_closed: bool
    next_action: str
  }
  class TargetRef {
    ecosystem: Ecosystem
    name: str
    version: str [0..1]
    artifact_sha256: str [0..1]
  }
  class Evidence {
    id: str, format EV-n
    kind: EvidenceKind
    trust: str
    severity: info | soft | hard
    observed: dict
    content_hash: sha256
  }
  class ExplanationSentence {
    text: str
    evidence_ids: list~str~
  }
  class SafeRemediation {
    status: str
    candidate: TargetRef [0..1]
    candidate_source: str
    verification_level: str
    approved_requirement: str
  }
  class RouterReceipt {
    total_cost_usd: float
    counterfactual_all_ultra_usd: float
    savings_pct: float
    tavily_calls: int
  }
  class RouteCall {
    stage: str
    tier: nano | super | ultra
    model_id: str
    prompt_tokens: int
    cost_usd: float
  }
  class Verdict {
    <<enumeration>>
    ALLOW
    REVIEW
    BLOCK
  }

  GateVerdict --> "1" TargetRef : target
  GateVerdict *-- "1..*" Evidence
  GateVerdict *-- "0..*" ExplanationSentence
  GateVerdict *-- "0..1" SafeRemediation
  GateVerdict *-- "0..1" RouterReceipt
  RouterReceipt *-- "1..*" RouteCall
  ExplanationSentence ..> Evidence : «cites»
  GateVerdict ..> Verdict
```