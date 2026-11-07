"""Small transparent lexical retriever. It returns public KB evidence, never fixture truth."""
import re
from .common import ValidationError

STOPWORDS = {"the", "a", "an", "to", "after", "and", "is", "it", "in", "of", "on", "when", "task"}

def tokens(text):
    return set(re.findall(r"[a-z0-9]+", text.lower())) - STOPWORDS

def retrieve(bug, knowledge_base):
    entries = knowledge_base.get("entries") if isinstance(knowledge_base, dict) else knowledge_base
    if not isinstance(entries, list) or not entries or len(entries) > 50:
        raise ValidationError("Knowledge base needs one to fifty public entries")
    query = tokens(bug["title"] + " " + bug["description"])
    scored = []
    ids = set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or entry["id"] in ids:
            raise ValidationError("Knowledge-base IDs must be unique strings")
        ids.add(entry["id"])
        keywords = entry.get("keywords", [])
        if not isinstance(keywords, list) or not all(isinstance(s, str) for s in keywords):
            raise ValidationError("Knowledge-base keywords must be strings")
        doc_tokens = tokens(" ".join([entry.get("title", ""), entry.get("description", "")] + keywords))
        matched = sorted(query & doc_tokens)
        scored.append({"entry": entry, "score": len(matched), "matched_terms": matched})
    scored.sort(key=lambda x: (-x["score"], x["entry"]["id"]))
    requested = bug.get("journey_id")
    if requested:
        candidates = [row for row in scored if row["entry"]["id"] == requested]
        if not candidates:
            raise ValidationError("Requested journey does not exist in the knowledge base")
        return candidates[0], scored
    if scored[0]["score"] < 2:
        raise ValidationError("Insufficient knowledge-base match; clarify the affected workflow")
    if len(scored) > 1 and scored[0]["score"] == scored[1]["score"]:
        raise ValidationError("Ambiguous knowledge-base match; clarify the affected workflow")
    return scored[0], scored
