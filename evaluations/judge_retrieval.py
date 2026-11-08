"""Deterministic retrieval of versioned judge-only rubric illustrations.

This module is not imported by the evaluated agent. References are untrusted
pedagogical material, never evidence about a current task or human calibration.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

from bug_validator.common import digest
from bug_validator.schemas import reject_duplicate_fields
from .semantic import DIMENSIONS, validate_judgment

DEFAULT_CORPUS = Path(__file__).with_name('data') / 'judge-references-v1.json'
MAX_BYTES = 128 * 1024
EXAMPLE_FIELDS = {'id', 'family', 'lineage', 'source_task_id', 'source_packet_sha256',
                  'split', 'provenance', 'tags', 'evidence', 'report', 'dimensions'}


def load_corpus(path=DEFAULT_CORPUS):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError('Judge corpus must be a bounded regular JSON file')
    corpus = json.loads(path.read_text(), object_pairs_hook=reject_duplicate_fields,
                        parse_constant=lambda v: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
    if (not isinstance(corpus, dict) or set(corpus) != {'schema_version', 'corpus_version', 'rubric_version', 'examples'}
            or corpus['schema_version'] != 1 or corpus['rubric_version'] != 'general-semantic-v2'
            or not isinstance(corpus['corpus_version'], str) or not corpus['corpus_version']):
        raise ValueError('Unsupported judge corpus schema or rubric')
    examples = corpus['examples']
    if not isinstance(examples, list) or not 1 <= len(examples) <= 100:
        raise ValueError('Corpus requires 1..100 reference examples')
    seen_ids, seen_content = set(), set()
    for row in examples:
        if not isinstance(row, dict) or set(row) != EXAMPLE_FIELDS:
            raise ValueError('Reference example fields must match the curated schema')
        for field in ['id', 'family', 'lineage', 'source_task_id']:
            if not isinstance(row[field], str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{1,99}', row[field]):
                raise ValueError('Invalid reference identity')
        if row['id'] in seen_ids or row['source_task_id'].startswith(('dev-', 'reserved-')):
            raise ValueError('Duplicate reference or evaluation-task contamination')
        seen_ids.add(row['id'])
        if row['split'] != 'judge-reference':
            raise ValueError('Only explicitly separated judge-reference examples can be retrieved')
        provenance = row['provenance']
        if (not isinstance(provenance, dict) or set(provenance) != {'kind', 'human_reviewed', 'source'}
                or provenance['kind'] != 'authored_synthetic' or provenance['human_reviewed'] is not False
                or not isinstance(provenance['source'], str) or not provenance['source'].strip()
                or row['source_packet_sha256'] is not None):
            raise ValueError('v1 corpus accepts only explicitly synthetic, non-human reference illustrations')
        if (not isinstance(row['tags'], list) or not 1 <= len(row['tags']) <= 20
                or any(not isinstance(t, str) or not re.fullmatch(r'[a-z][a-z_-]{1,39}', t) for t in row['tags'])):
            raise ValueError('Invalid reference tags')
        for field in ['evidence', 'report']:
            if not isinstance(row[field], str) or not 1 <= len(row[field]) <= 4000:
                raise ValueError('Reference text missing or over budget')
        validate_judgment({'dimensions': row['dimensions']})
        if any(set(v) != {'label', 'rationale'} or len(v['rationale']) > 1500 for v in row['dimensions'].values()):
            raise ValueError('Reference rationale over budget')
        content = digest({'evidence': row['evidence'], 'report': row['report']})
        if content in seen_content:
            raise ValueError('Duplicate reference content')
        seen_content.add(content)
    return corpus


def normalized_text(value):
    return ' '.join(re.findall(r'[a-z0-9]+', value.lower()))


def text_values(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from text_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from text_values(child)


def tokens(value):
    return set(re.findall(r'[a-z]{3,40}', value.lower()))


def retrieve(corpus, packet, context, limit=3):
    """Rank independently authored references; hard-exclude family and lineage.

    Query uses public task/report text only, never expected verdict or grader
    results. Stable ID tie-breaking makes the retrieval receipt reproducible.
    """
    if type(limit) is not int or not 0 <= limit <= 5:
        raise ValueError('Reference count must be 0..5')
    if not all(isinstance(context.get(k), str) and context[k] for k in ('task_id', 'family', 'lineage')):
        raise ValueError('Retrieval requires task, family and lineage exclusion context')
    query = json.dumps({'bug': packet['public_bug'], 'report': packet['target']}, sort_keys=True)
    query_tokens = tokens(query)
    current_text = {normalized_text(v) for v in text_values(packet) if len(v) >= 40}
    current_text.add(normalized_text(json.dumps(packet['target'], sort_keys=True)))
    ranking, excluded = [], []
    for row in corpus['examples']:
        reason = next((reason for reason, matches in [
            ('same_task', row['source_task_id'] == context['task_id']),
            ('same_family', row['family'] == context['family']),
            ('same_lineage', row['lineage'] == context['lineage']),
            ('exact_current_text_copy', any(normalized_text(row[key]) in current_text for key in ('report', 'evidence')))] if matches), None)
        if reason:
            excluded.append({'id': row['id'], 'reason': reason})
            continue
        reference_tokens = tokens(' '.join(row['tags']) + ' ' + row['evidence'] + ' ' + row['report'])
        overlap = sorted(query_tokens & reference_tokens)
        score = len(overlap)
        if score:
            ranking.append((score, row['id'], overlap, row))
    ranking.sort(key=lambda item: (-item[0], item[1]))
    selected = ranking[:limit]
    return [row for _, _, _, row in selected], {
        'algorithm': 'token-overlap-v1', 'corpus_version': corpus['corpus_version'],
        'corpus_sha256': digest(corpus), 'query_sha256': digest(query),
        'exclusion_context': context, 'excluded': excluded,
        'selected': [{'id': ref_id, 'score': score, 'matching_tokens': overlap,
                      'example_sha256': digest(row)} for score, ref_id, overlap, row in selected],
        'qualification': 'Synthetic rubric illustrations, not human labels or evidence for this trial',
    }
