# Offline evidence corpus

Drop additional open-access papers here as `.json` files to extend the offline evidence
corpus. Each file may hold one object or an array of objects with these fields:

```json
{
  "external_id": "PMID:12345678",
  "title": "...",
  "journal": "...",
  "year": "2024",
  "doi": "10.xxxx/yyyy",
  "url": "https://pubmed.ncbi.nlm.nih.gov/12345678/",
  "abstract": "...",
  "keywords": ["outdoor", "progression"]
}
```

They are merged with the built-in list in `app/evidence/corpus.py` and are used whenever
live retrieval is unavailable or `EVIDENCE_OFFLINE=true`.

Only add works you are permitted to redistribute. Metadata and abstracts of open-access
articles are generally fine; full paywalled texts are not.
