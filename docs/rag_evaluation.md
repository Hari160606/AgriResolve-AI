# Phase 13 — AI field inspection assistant: evaluation notes

Code: `src/rag_assistant/{ingest,index,answer,evaluate}.py` · Page: `app/views/assistant.py`

## What is running right now

| Item | Value |
|---|---|
| Corpus | `guidelines_pdfs/demo_field_notes.md` — **one internal demo note, not an official publication** |
| Chunks | 7 (≈900 characters each, 150-character overlap, page 1) |
| Retrieval mode | **TF-IDF fallback** (`sentence-transformers` and `faiss-cpu` are not installed) |
| Generation | **Ollama `llama3`** on `http://localhost:11434` — reachable and working |
| Citations | document + page shown for every retrieved passage |

The target stack (Sentence Transformers + FAISS) is implemented in `index.py` and activates
automatically once those packages are installed; `index_status()` reports which mode is in use and the
UI states it, so retrieval quality is never overstated.

## Retrieval evaluation (run, not estimated)

```bash
python -m src.rag_assistant.evaluate
```

| # | Question | Expected keyword | Hit | Top score |
|---|---|---|---|---|
| 1 | What should I check first in a paddy field with planthopper hoppers? | hopper | ✅ | 0.246 |
| 2 | How do I confirm drought stress in a ragi field? | drought | ✅ | 0.292 |
| 3 | Which symptoms suggest blast disease in paddy? | blast | ✅ | 0.178 |
| 4 | What is the inspection checklist for a waterlogged sugarcane field? | waterlog | ✅ | 0.221 |
| 5 | What should the officer ask the farmer about affected area? | area | ✅ | 0.397 |

**Retrieval hit rate: 5/5 = 100 % on a 7-chunk corpus.**

That number is close to meaningless as a quality signal — the corpus is tiny, the questions were
written by looking at the note, and TF-IDF rewards exact keyword overlap. It proves the plumbing
(chunking → retrieval → prompt → citations) works; it says nothing about performance on a real
package-of-practices PDF.

## Answer behaviour observed

- With Ollama running, answers are short, bulleted and cite `[1]`/`[2]` inline, restricted to the
  retrieved passage (example: the planthopper answer reproduces the "part the tillers, count hoppers
  per hill" instruction).
- With Ollama stopped, the assistant falls back to an extractive answer that quotes the retrieved
  passages and says explicitly that no generation happened.
- With an empty index, it says no guidelines are available and does not answer.
- With nothing above the similarity floor, it replies "The provided guidelines do not cover this."

## Not evaluated (honest gaps)

1. **No official PDFs.** ICAR/UAS/Department of Agriculture documents are not bundled (licence and
   size); `src/ingestion/download_guidelines.py` lists the sources and the metadata to record. Until
   they are added, every answer about real pesticide doses, schemes or thresholds is out of scope.
2. **No retrieval quality on real documents** — sentence-transformer embeddings, page-level chunking of
   scanned PDFs and OCR quality are untested.
3. **No answer-grounding metric** (faithfulness, hallucination rate). Manual spot checks are not a
   substitute; if this goes further, run a small labelled set through both retrievers and score
   citation correctness.
4. **No latency numbers** — `llama3` on a laptop CPU is fast enough for a demo but was not benchmarked.

## Reproduce

```bash
python -m src.rag_assistant.ingest          # extract chunks
python -m src.rag_assistant.index           # report retrieval mode
python -m src.rag_assistant.evaluate        # hit-rate table + one generated answer
```

To use the real stack:

```bash
pip install sentence-transformers faiss-cpu PyMuPDF
# drop official PDFs into guidelines_pdfs/
python -m src.rag_assistant.ingest && python -m src.rag_assistant.evaluate
```
