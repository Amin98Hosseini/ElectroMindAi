You are working on my existing GitHub project:

https://github.com/Amin98Hosseini/ElectroMindAi/

I want you to implement a new feature called **Laya Context Intelligence**.

## Goal

Integrate the **Laya AI decision model** into the existing ElectroMindAi RAG pipeline.

The current architecture already uses:

- ChromaDB for project-document retrieval
- RAG/context building
- llama.cpp / llama-server for the final LLM
- PyQt6 UI
- configurable RAG settings
- local models

I do NOT want Laya to replace the existing LLM.

The desired architecture is:

```text
User Question
      │
      ▼
ChromaDB Retrieval
      │
      │  retrieve high-recall candidates
      ▼
Candidate Contexts
      │
      ▼
Laya AI
      │
      │  determine relevance of each context
      ▼
Relevant / Ranked Contexts
      │
      ▼
Existing RAG Context Builder
      │
      ▼
Existing llama.cpp LLM
      │
      ▼
Final Answer
```

Laya should act as a **context-selection / relevance-ranking layer** between retrieval and the final LLM.

---

# 1. First inspect the repository

Before changing anything:

1. Inspect the complete repository structure.
2. Understand how:
   - RAG retrieval works
   - ChromaDB is initialized
   - settings are stored
   - settings UI is implemented
   - the current `_send()` chat pipeline works
   - `ChatWorker` works
   - LLM requests are sent to llama.cpp
3. Identify the smallest clean architectural changes required.
4. Do not rewrite unrelated code.
5. Preserve all existing functionality.

Important existing components are likely around:

```text
core/
rag/
ui/
```

Pay particular attention to:

```text
core/config.py
core/prompts.py
rag/store.py
rag/indexer.py
ui/main_window.py
ui/workers.py
```

Use the actual repository structure rather than assuming these files are unchanged.

---

# 2. Laya integration

Use the Laya model described here:

https://huggingface.co/blog/sora-2/laya-ai-model-how-it-works-run-it-locally-and-eval

Also verify the current official Laya Python API/documentation before implementing it.

Laya is a decision model, not a chatbot.

Do NOT ask Laya to generate natural-language answers.

Its job is to decide whether a retrieved context is relevant to the user's question.

Prefer the Laya decision type:

```text
noul
```

for determining relevance/probability.

Conceptually:

```text
state = {
    question: user_question,
    context: candidate_context
}

question = {
    relevant: {
        type: "noul",
        instructions: "Determine whether this context is relevant to answering the user's question."
    }
}
```

However, verify the exact current Laya API before writing the implementation.

Do not invent unsupported APIs or constructor arguments.

---

# 3. Context-selection algorithm

Implement the following pipeline:

### Step 1 — Initial retrieval

Instead of immediately retrieving only the final number of contexts, retrieve a larger candidate set.

For example:

```text
RAG top_k = 10
```

if the user has configured:

```text
Final context count = 4
```

The general flow should be:

```text
ChromaDB:
    top 10 candidates

        ↓

Laya:
    relevance scoring

        ↓

Sort by Laya relevance

        ↓

Apply relevance threshold

        ↓

Keep maximum 4 contexts

        ↓

Existing LLM
```

The values must be configurable.

Suggested defaults:

```json
{
    "enabled": true,
    "initial_top_k": 10,
    "final_top_k": 4,
    "threshold": 0.70
}
```

Do NOT claim that `0.70` is scientifically optimal. It is only a configurable default.

---

# 4. Important distinction

Laya is being used for:

```text
context relevance / context selection
```

NOT:

```text
fact checking
truth verification
answer generation
```

Do not describe a context as "factually correct" merely because Laya selected it.

The implementation and UI should use terminology such as:

- Relevant
- Relevance score
- Context selection
- Context filtering
- Context ranking

---

# 5. Create a clean Laya abstraction

Create a dedicated module/class rather than putting Laya logic directly inside the UI.

For example, something conceptually similar to:

```text
core/laya.py
```

or another location that fits the existing architecture.

The class should:

- lazily initialize the Laya model
- expose a simple relevance-scoring API
- hide Laya-specific implementation details
- handle initialization errors
- support multilingual operation
- avoid loading Laya unnecessarily when disabled

Conceptual API:

```python
score_context(question, context) -> float
```

and/or:

```python
rank_contexts(question, contexts) -> ranked_contexts
```

Use the actual project's coding style.

---

# 6. Multilingual support

ElectroMindAi can be used with English, Persian, and mixed-language technical questions.

Therefore, prefer the appropriate multilingual Laya model if supported by the current official Laya implementation.

Do not hard-code assumptions about the model name.

Verify the currently supported model identifiers from the official documentation/package.

Make the Laya model configurable.

---

# 7. RAG pipeline integration

Modify the existing chat flow so that the current architecture becomes:

```python
user_query
    ↓
rag.retrieve(...)
    ↓
Laya context filtering/ranking
    ↓
rag.build_context(...)
    ↓
LLM
```

Do not duplicate RAG logic.

Do not create a second independent RAG implementation.

Reuse the existing:

```python
rag.retrieve(...)
rag.build_context(...)
```

where appropriate.

The final selected source paths must still be stored in the existing mechanism:

```python
_pending_sources
```

or whatever equivalent exists in the current repository.

This is important because existing source/citation UI must continue working.

---

# 8. Preserve fallback behavior

The application must continue working if Laya is:

- disabled
- not installed
- unable to load
- incompatible with the current Python environment
- unable to perform inference

When Laya is disabled:

```text
ChromaDB → existing context builder → LLM
```

When Laya fails:

Prefer a graceful fallback to:

```text
ChromaDB → existing context builder → LLM
```

unless the existing application has a better error-handling convention.

The application must not crash simply because Laya is unavailable.

Clearly log the failure.

---

# 9. Do not block the PyQt6 GUI

Inspect the existing worker/thread architecture.

Laya inference and model initialization must NOT freeze the PyQt6 interface.

If necessary, implement a worker such as:

```text
ContextFilterWorker
```

or integrate it into the existing worker architecture.

Preferred flow:

```text
_send()
   ↓
Context/RAG worker
   ├── ChromaDB retrieval
   ├── Laya scoring
   ├── ranking/filtering
   └── return selected contexts
           ↓
       ChatWorker
           ↓
       llama.cpp
```

Do not perform expensive Laya inference directly on the GUI thread if it can noticeably block the interface.

Follow the project's existing threading conventions.

---

# 10. Settings

Add Laya configuration to the existing settings system rather than creating a completely separate configuration mechanism.

Add settings for approximately:

```text
Enable Laya Context Intelligence
Laya Model
Initial RAG Candidates
Final Context Count
Laya Relevance Threshold
```

Suggested defaults:

```text
Enabled: true
Initial candidates: 10
Final contexts: 4
Threshold: 0.70
```

Again, verify the existing settings architecture and integrate into it cleanly.

Settings must persist between application launches.

---

# 11. UI

Add the Laya controls to the existing settings/RAG area.

Do not redesign the entire application UI.

Keep the existing visual style.

Suggested UI:

```text
RAG
────────────────────────────
☑ Enable RAG

Top K: 4

Laya Context Intelligence
☑ Enable Laya filtering

Initial candidates: 10
Final contexts: 4
Relevance threshold: 0.70
Model: multilingual
```

Use the project's existing widgets/styles/layout conventions.

---

# 12. Diagnostics

Add useful logging/debug information.

For example:

```text
RAG retrieved: 10 contexts
Laya evaluated: 10 contexts
Laya selected: 4 contexts
```

For each selected/filtered context, optionally log:

```text
0.94  src/foo.py
0.89  docs/stm32.md
0.82  README.md
0.41  unrelated.py
```

Do not expose excessive internal information to normal users.

If the application already has a debug/logging mechanism, reuse it.

---

# 13. Performance

Avoid unnecessary model loading.

Laya should ideally be loaded once and reused.

Do not initialize the Laya model for every retrieved context.

Bad:

```text
context 1 → load model
context 2 → load model
context 3 → load model
```

Good:

```text
application/session starts
        ↓
Laya initialized once
        ↓
multiple context evaluations
```

Use lazy initialization if possible:

```text
Laya disabled → no model loaded
Laya enabled → initialize when first needed
```

Do not load Laya if RAG is disabled.

---

# 14. Batch inference

Investigate whether the current Laya API supports evaluating multiple context decisions efficiently in one call.

If the official API supports this cleanly, use batching.

If not, implement a safe sequential approach.

Do not invent an unsupported batch API.

Correctness and maintainability are more important than premature optimization.

---

# 15. Context size

Do not send the entire project to Laya.

The intended flow is:

```text
large project
    ↓
ChromaDB retrieval
    ↓
small set of candidate chunks
    ↓
Laya
```

Each Laya decision should contain enough information to evaluate relevance but avoid unnecessarily huge state.

Remember that Laya itself has context-length constraints.

---

# 16. Source metadata

Preserve existing metadata.

A candidate should continue to contain information such as:

```python
{
    "text": "...",
    "path": "src/example.py"
}
```

If useful, internally maintain:

```python
{
    "text": "...",
    "path": "...",
    "rag_score": ...,
    "laya_score": ...
}
```

Do not break existing `retrieve()` consumers.

Prefer adding fields over changing the existing API incompatibly.

---

# 17. Ranking logic

The preferred logic is:

```text
candidate contexts
        ↓
Laya relevance score
        ↓
remove contexts below threshold
        ↓
sort descending by Laya score
        ↓
take final_top_k
```

Example:

```text
Context A → 0.94
Context B → 0.89
Context C → 0.83
Context D → 0.71
Context E → 0.42
```

With:

```text
threshold = 0.70
final_top_k = 4
```

the final context would contain:

```text
A
B
C
D
```

Do not hard-code these example values.

---

# 18. Avoid losing useful contexts

Consider the case where all Laya scores are below the threshold.

Do not automatically send an empty context to the LLM.

Implement a sensible fallback policy.

For example:

```text
If enough contexts pass threshold:
    use filtered contexts

If too few pass:
    use the highest-scoring contexts up to final_top_k

If Laya fails:
    use original RAG results
```

Document this behavior in the code.

---

# 19. Compatibility

The existing application uses local llama.cpp.

Do NOT try to run Laya through llama.cpp unless the verified Laya implementation explicitly supports that and there is a strong reason to do so.

Laya should be treated as a separate local model/component.

The architecture should remain:

```text
Laya
  ↓
context decision
  ↓
llama.cpp
  ↓
final generation
```

---

# 20. Dependencies

Inspect the existing dependency files.

Add the required Laya dependency using the project's current dependency-management approach.

Do not blindly overwrite dependency versions.

Check the currently supported Laya package/version and Python requirements.

The application should clearly communicate if the Laya dependency is missing.

---

# 21. Documentation

Update the project documentation.

Add a section explaining:

```text
Laya Context Intelligence
```

Explain:

1. What Laya does.
2. Why it is used.
3. Where it sits in the architecture.
4. How RAG retrieval works with Laya.
5. Configuration options.
6. How to disable it.
7. Fallback behavior.
8. Installation requirements.
9. Difference between Laya relevance selection and LLM generation.

Include an architecture diagram such as:

```text
User
 │
 ▼
ElectroMindAi
 │
 ▼
ChromaDB RAG
 │
 │  Top-N candidate contexts
 ▼
Laya Decision Model
 │
 │  relevance scores
 ▼
Context Filter / Ranker
 │
 │  Top-K contexts
 ▼
llama.cpp LLM
 │
 ▼
Answer
```

---

# 22. Tests

Add tests for the new functionality.

At minimum test:

### Laya disabled

```text
RAG → LLM
```

### Laya enabled

```text
RAG → Laya → LLM
```

### Laya failure

```text
RAG → Laya failure → fallback RAG → LLM
```

### Threshold

Verify contexts below the configured threshold are filtered appropriately.

### Top-K

Verify no more than `final_top_k` contexts are passed to the LLM.

### Empty results

Verify the application handles:

```text
no RAG results
```

### Missing Laya dependency

The application should not crash at startup.

Use mocks where appropriate so tests do not require downloading a large model.

---

# 23. Important architectural principle

Do not turn Laya into another chatbot.

The responsibilities should remain:

```text
ChromaDB
    = retrieve candidate knowledge

Laya
    = decide/rank which retrieved knowledge is relevant

LLM
    = reason, synthesize and generate the final answer
```

This separation is important.

---

# 24. Code quality requirements

Follow the existing project's:

- naming conventions
- formatting
- architecture
- logging
- error handling
- threading model
- settings model
- UI patterns

Avoid unnecessary refactoring.

Avoid changing public APIs unless necessary.

Keep changes modular.

Use type hints where the existing project uses them.

Add useful comments/docstrings, but do not over-comment obvious code.

---

# 25. Before implementation

First inspect the repository and identify:

```text
1. Current RAG pipeline
2. Current settings architecture
3. Current worker/thread architecture
4. Current dependency management
5. Current UI settings location
6. Current source/citation handling
```

Then briefly explain your implementation plan.

After that, implement the feature completely.

Do not stop after creating a design document.

---

# 26. After implementation

Run the available tests/lint/type checks if present.

Also perform a basic end-to-end validation of:

```text
User question
→ ChromaDB retrieval
→ Laya filtering
→ selected contexts
→ llama.cpp
→ final answer
```

Check for:

- import errors
- missing dependencies
- Qt thread errors
- settings persistence problems
- incorrect Laya API usage
- context formatting problems
- broken source references
- regressions in normal RAG mode

---

# 27. Final response from you

When finished, report:

```text
Implemented:
- ...
- ...
- ...

Files changed:
- ...
- ...

New settings:
- ...
- ...

Pipeline:
User → ChromaDB → Laya → Context Filter → llama.cpp → Answer

Tests:
- ...
```

Also clearly mention:

- how to install Laya
- how to enable/disable it
- any Python-version requirements
- any limitations discovered during implementation

Most importantly, do not claim that Laya verifies factual correctness. It is being used as a relevance/context-selection layer.

Start by inspecting the repository and the official Laya API, then implement the feature.