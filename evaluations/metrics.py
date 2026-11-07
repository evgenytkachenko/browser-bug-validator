"""Small-sample summaries. Trial repeats are not evidence of population independence."""
import math
from collections import defaultdict


def wilson(successes, total, z=1.959963984540054):
    if not total:
        return None
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1-p) / total + z*z / (4 * total * total)) / denominator
    return [max(0.0, center-half), min(1.0, center+half)]


def summarize(records):
    groups = defaultdict(list)
    for row in records:
        groups[row['task_id']].append(row)
    by_task = {}
    for task_id, rows in groups.items():
        outcomes = [bool(r.get('deterministic_pass')) for r in rows]
        by_task[task_id] = {'n': len(rows), 'successes': sum(outcomes), 'trial_pass_rate': sum(outcomes)/len(rows),
                            'all_trials_passed': all(outcomes), 'at_least_one_passed': any(outcomes),
                            'outcomes': outcomes}
    successes = sum(bool(r.get('deterministic_pass')) for r in records)
    return {'trials': len(records), 'successes': successes, 'failures': len(records)-successes,
            'trial_pass_rate': successes/len(records) if records else None,
            'descriptive_wilson_95': wilson(successes, len(records)),
            'empirical_any_trial_task_rate': sum(v['at_least_one_passed'] for v in by_task.values())/len(by_task) if by_task else None,
            'empirical_all_trials_task_rate': sum(v['all_trials_passed'] for v in by_task.values())/len(by_task) if by_task else None,
            'by_task': by_task, 'semantic_status': 'unverified',
            'limitations': ['Development fixtures only; no fresh holdout was run.',
                            'Descriptive intervals do not establish generalization or independent sampling.',
                            'Repeated deterministic runs measure execution stability, not model variation.',
                            'Any/all trial rates describe observed groups and are not population pass@k/pass^k estimates.']}
