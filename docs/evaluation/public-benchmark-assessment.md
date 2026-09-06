# Public Benchmark Assessment (Layer B Evaluation Analysis)

## 1. Executive Summary

According to the EvidenceOps Single Source of Truth ([EvidenceOps_SSOT.md](file:///d:/Code/Assignment/EvidenceOps/EvidenceOps_SSOT.md)), evaluation is structured into two potential layers:
- **Layer A (Primary / Authoritative)**: A controlled evaluation dataset grounded directly in the local technical documentation corpus (10 documents, 52 chunks).
- **Layer B (Secondary / Comparative)**: An optional public benchmark slice intended to demonstrate transferability on standardized RAG tasks.

This document formally records the technical assessment of standard public RAG benchmarks (HotpotQA, Natural Questions, MS MARCO, and BEIR) against the constraints and requirements of EvidenceOps Phase 4.

## 2. Benchmark Candidates Evaluated

| Benchmark | Domain | Corpus Size | Characteristics & Misalignments |
| :--- | :--- | :--- | :--- |
| **HotpotQA** | Wikipedia | ~5M docs | Multi-hop reasoning across general Wikipedia biographies and geography. Relies heavily on broad world knowledge. Zero overlap with technical API specifications (Qdrant, FastAPI, LangGraph, Ollama). |
| **Natural Questions (NQ)** | Wikipedia | ~300k docs | Google search queries paired with Wikipedia extract answers. Factual lookup of common knowledge, pop culture, and history. |
| **MS MARCO** | Bing Web Search | ~8.8M passages | Broad web search snippets. Many answers are short phrases or entity names. High noise in passage quality and lack of structured code/API concepts. |
| **BEIR (NFCorpus, SciFact, FiQA)** | Mixed specialized | 10k–50k docs per sub-dataset | Domain-specific retrieval benchmarks (biomedical, finance, scientific facts). Strong for retrieval evaluation, but lacks generative citation validation grounded in software architecture. |

## 3. Core Architectural and Methodological Conflicts

1. **Corpus Incompatibility**:
   - EvidenceOps is designed and calibrated for an authoritative, high-integrity technical corpus (FastAPI, Qdrant, Ollama, LangGraph, FastEmbed, FlashRank, Pydantic-Settings).
   - Evaluating on HotpotQA or NQ would require indexing thousands or millions of general Wikipedia documents, which directly violates the 8 GB RAM, local-first CPU budget (Ryzen 5 5600G).
   - If instead a tiny subset of Wikipedia documents were indexed, the questions would no longer represent realistic retrieval distributions (retrieving 5 chunks out of 52 is fundamentally different from retrieving 5 chunks out of 5,000,000).

2. **Absence of Grounded Citation Verification**:
   - Public benchmarks evaluate lexical match or semantic similarity against reference answers.
   - EvidenceOps evaluates **exact citation validity** (every claim must map to `[C#]` referencing a verified chunk ID) and **hallucination prevention via abstention**. Public datasets do not provide chunk-level citation supervision for local technical documents.

3. **Risk of Metric Corruption**:
   - Forcing public questions onto our 10-document technical corpus would result in near-100% unanswerable queries (artificial abstention rate) or require synthetically corrupting the queries to fit the technical corpus, defeating the purpose of an external benchmark.

## 4. Methodological Decision for Phase 4

- **Layer A is Authoritative**: EvidenceOps Phase 4 standardizes on `evidenceops-controlled-v1.json` (100 controlled questions: 60 dev / 20 val / 20 test), featuring:
  - 30 Single Fact questions (exact parameter, interface, and identifier retrieval).
  - 25 Multi-Hop questions (requiring multi-chunk evidence synthesis).
  - 20 Contrastive questions (differentiating options, endpoints, and behaviors).
  - 10 Temporal / Ambiguous questions (version differences and migration patterns).
  - 15 Unanswerable questions (testing strict abstention when evidence is absent).
- **Zero Leakage**: Strict split separation enforced by SHA-256 cryptographic identity (`evidenceops-controlled-v1.identity.json`) and provenance auditing (`evidenceops-controlled-v1.provenance.json`).
- **Deterministic Scoring**: Primary metrics are computed via deterministic atomic gold-fact verification, citation support checks, and IR metrics (Recall@K, MRR@10, nDCG@10), ensuring reproducible, zero-cost, local-first evaluation.
