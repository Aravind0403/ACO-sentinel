# ACO-Sentinel: Engineering Design Dossier (Index)

Welcome to the definitive reference and engineering design record for the **ACO-Sentinel (Version 2)** scheduling system. This dossier captures the complete high-level and low-level designs, mathematical foundations, distributed systems properties, failure modes, operational practices, and interview-defense scenarios for the scheduler control plane.

---

## Navigation Blueprint

### Section A: High-Level Foundations
*   [00. Overview](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/00_overview.md) — Executive summary, core vision, and design pillars.
*   [01. Problem Definition](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/01_problem_definition.md) — Motivation, limits of the default K8s scheduler, and AI workload requirements.
*   [02. Requirements and Constraints](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/02_requirements_and_constraints.md) — SLA limits, latency budgets, and security/scale constraints.
*   [03. High-Level Design (HLD)](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/03_hld.md) — Control plane topology, gRPC loopback protocols, and telemetry pipelines.

### Section B: Implementation Tour & Low-Level Design (LLD)
*   [04. Low-Level Design (LLD)](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/04_lld.md) — Classes, Go structs, interfaces, and concurrency primitives.
*   [05. Repository Walkthrough](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/05_repository_walkthrough.md) — Folder layout, module maps, and compilation scopes.
*   [06. Component Breakdown](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/06_component_breakdown.md) — Telemetry agents, cost engine interfaces, and circuit breakers.
*   [07. File Walkthrough](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/07_file_walkthrough.md) — Module by module source file ownership.
*   [08. Function Deep Dive](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/08_function_deep_dive.md) — Method contracts, input/output constraints, and thread-safety models.
*   [09. Code Path Analysis](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/09_code_path_analysis.md) — Scheduling cycle traces, error pathways, and rollback transitions.

### Section C: Infrastructure & Core Concepts
*   [10. Kubernetes Scheduler Framework](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/10_kubernetes_scheduler_framework.md) — Complete analysis of hooks from QueueSort to PostBind.
*   [11. Distributed Systems Concepts](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/11_distributed_systems.md) — PACELC bounds, consensus boundaries, and clock drift assumptions.
*   [12. Concurrency and Transactions](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/12_concurrency_and_transactions.md) — TOCTOU analysis, optimistic locks, and Unreserve rollbacks.
*   [13. Algorithms and Mathematics](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/13_algorithms_and_math.md) — LaTeX derivations, trust calculations, EMA properties, and ACO convergence.
*   [14. Performance Engineering](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/14_performance_engineering.md) — CPU/Memory profiles, allocation budgets, and empirical GKE benchmarks across CPU & GPU nodes.
*   [GKE Control-Plane Benchmarks](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/GKE_BENCHMARKS.md) — Recorded empirical benchmarks on GKE CPU (`e2-medium`) & NVIDIA GPU (`g2-standard-4` L4) nodes.

### Section D: Production Operations & Security
*   [15. Observability](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/15_observability.md) — Prometheus metrics scrapers, audit paths, and telemetry dashboards.
*   [16. Security](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/16_security.md) — RBAC definitions, TLS configurations, and annotation authentication.
*   [17. Failure Modes & Recovery Matrix](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/17_failure_modes.md) — Self-healing mappings and network partition recovery.
*   [18. Scalability & Sharding](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/18_scalability.md) — Path to 100k nodes, multi-cluster federation, and sharding models.

### Section E: Architecture Decision Records (ADRs)
*   [ADR-001: why framework instead of extender](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/adr/001_framework_vs_extender.md)
*   [ADR-002: why go + python language split](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/adr/002_go_plus_python.md)
*   [ADR-003: why grpc loopback over HTTP REST](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/adr/003_grpc_vs_rest.md)
*   [ADR-004: why protobuf instead of JSON encoding](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/adr/004_protobuf_vs_json.md)
*   [ADR-005: why optimistic reservation](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/adr/005_optimistic_reservation.md)
*   [ADR-006: why PostBind transactional commit](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/adr/006_postbind_commit.md)
*   [ADR-007: why multiplicative composite trust](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/adr/007_multiplicative_trust.md)
*   [ADR-008: why Ant Colony Optimization for heuristic search](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/adr/008_aco.md)
*   [ADR-009: why control-plane Sentinel sidecar](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/adr/009_node_local_daemon.md)
*   [ADR-010: why asynchronous telemetry updates](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/adr/010_async_telemetry.md)

### Section F: Interview Defense Loops
*   [19. Tradeoffs Summary](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/19_tradeoffs.md) — Critical compromises and limitation parameters.
*   [20. Design Alternatives](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/20_design_alternatives.md) — Comparative matrices (Volcano, Kueue, Koordinator).
*   [21. Interview Questions (1000+)](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/21_interview_questions.md) — Comprehensive technical Q&A categorized by subject.
*   [22. Mock Interview Scripts](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/22_mock_interviews.md) — Simulating interactive loops with Staff/Principal interviewers.
*   [Interview Pitch (90s)](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/Interview_Intro_pitch.md) — Fast Problem-to-Impact elevator pitch script.
*   [Resume Points](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/resume.md) — High-impact, quantified resume bullet points for Staff/Principal roles.
*   [Glossary](file:///Users/aravindsundaresan/Development/ACO_Project_Front/ACO_Project_Upfront_V2/learning/dossier/glossary.md) — Definition reference for scheduler terms.
