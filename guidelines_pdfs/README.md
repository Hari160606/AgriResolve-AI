# guidelines_pdfs/

Place official agricultural guideline PDFs here (ICAR, UAS Bangalore, Karnataka
Department of Agriculture "package of practices"). PDFs are **git-ignored** because of
licence and size; use `python -m src.ingestion.download_guidelines` for the documented
sources and download instructions.

`demo_field_notes.md` is committed on purpose: it is an **internal demo note written for
this prototype**, not an official publication. It exists so the retrieval pipeline and the
AI assistant page can be demonstrated without pretending to ship government documents.

After adding PDFs, rebuild the index:

```bash
python -m src.rag_assistant.ingest
python -m src.rag_assistant.index
python -m src.rag_assistant.evaluate
```
