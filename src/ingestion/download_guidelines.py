"""Where to obtain official agricultural guideline documents for the RAG assistant.

This module does not ship or download PDFs automatically: licences differ per publisher and
the files are large. It lists the organisations to source documents from and the metadata you
must record for each file, so ``docs/data_sources.md`` stays accurate.

Record for every document: title, organisation, page URL you used, licence/copyright note,
download date, page count, and whether redistribution is allowed.
"""

from __future__ import annotations

import csv

from src.config.settings import project_path

#: Organisations to source package-of-practices / advisory documents from.
ORGANISATIONS: list[dict[str, str]] = [
    {
        "organisation": "University of Agricultural Sciences (UAS), Bengaluru",
        "what": "Package of Practices for crops of Karnataka (crop-wise recommendations)",
        "where": "UAS Bengaluru publications page - record the exact URL you used",
    },
    {
        "organisation": "ICAR (Indian Council of Agricultural Research)",
        "what": "Crop protection advisories and package of practices for field crops",
        "where": "ICAR publication pages / KVK bulletins - record the exact URL",
    },
    {
        "organisation": "Department of Agriculture, Government of Karnataka",
        "what": "State advisories, scheme circulars and crop management notes",
        "where": "Raitha Mitra / department portal - record the exact URL",
    },
    {
        "organisation": "Directorate of Plant Protection, Quarantine & Storage",
        "what": "Pest surveillance and locust/armyworm advisories",
        "where": "PPQS advisories - record the exact URL",
    },
]

FIELDS = ["file_name", "title", "organisation", "source_url", "licence", "download_date", "page_count", "notes"]


def main() -> None:
    """Print the sourcing checklist and create a metadata template CSV."""
    print("Official guideline sources to collect (put PDFs in guidelines_pdfs/):\n")
    for item in ORGANISATIONS:
        print(f"- {item['organisation']}\n    {item['what']}\n    {item['where']}\n")

    template = project_path("data", "derived", "guideline_documents.csv")
    template.parent.mkdir(parents=True, exist_ok=True)
    if not template.exists():
        with template.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
    print(f"Metadata template: {template.relative_to(project_path())}")
    print(
        "After adding PDFs run:\n"
        "  python -m src.rag_assistant.ingest\n"
        "  python -m src.rag_assistant.index\n"
        "  python -m src.rag_assistant.evaluate"
    )


if __name__ == "__main__":
    main()
