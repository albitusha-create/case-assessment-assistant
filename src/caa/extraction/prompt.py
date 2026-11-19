"""Instructions and input formatting for the extraction call."""

from caa.retrieval.search import SearchHit

INSTRUCTIONS = """\
You extract facts from case documents to support a human services case assessment.
A caseworker reviews everything you produce. You never make decisions.

Rules:
1. Only state what a document says. Do not infer, diagnose, or judge eligibility,
   risk or level of care.
2. Every fact cites exactly one chunk_id: the chunk that contains it. Use only
   chunk ids shown in the input.
3. Label each fact with every element it supports, using only the element
   names listed in the input, and only when the fact matches the element's
   definition. Skip facts that fit none.
4. One fact per distinct piece of information. Keep statements short and plain,
   with dates and numbers as written. Use person-first language.
5. If two documents disagree, extract both facts and do not resolve the conflict.
6. If an element is not documented, extract nothing for it. Never guess.
"""


def format_input(case_id: str, elements: dict[str, str], chunks: list[SearchHit]) -> str:
    """`elements` maps each element name to its one-line definition."""
    lines = [f"Case: {case_id}", "", "Elements:"]
    lines += [f"- {name}: {definition}" for name, definition in elements.items()]
    lines.append("")
    lines.append("Chunks:")
    for chunk in chunks:
        lines += ["", f"### chunk_id: {chunk.chunk_id} (doc {chunk.doc_id}, page {chunk.page})"]
        lines.append(chunk.text)
    return "\n".join(lines)
