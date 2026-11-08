"""Descriptive repeated-task metrics, never independent population evidence."""
from collections import Counter, defaultdict
from math import comb, isfinite
from statistics import mean, median


def failure_category(row):
    if row.get('deterministic_pass') is True:
        return 'passed'
    if row.get('grader_error'):
        return 'harness_grader_error'
    state = row.get('process_status', {}).get('state')
    if state == 'launch_error':
        return 'infrastructure_launch_error'
    if state == 'timeout':
        return 'execution_timeout_unattributed'
    if row.get('model_calls_attempted', 0) > row.get('model_calls_completed', 0):
        return 'model_or_schema_error'
    if row.get('process_status', {}).get('report_error'):
        return 'agent_report_error'
    # A missing runtime/counter is not evidence that startup failed. This bucket
    # also includes preflight/config rejection and does not assert infrastructure blame.
    if row.get('requires_exercise') is True and row.get('browser_started') is False and type(row.get('model_calls_attempted')) is int and row['model_calls_attempted'] == 0:
        return 'browser_startup_or_predecision_failure'
    return 'agent_or_evidence_failure'


def summarize_trials(rows, ks=None):
    rows = list(rows)
    groups = defaultdict(list)
    ids = set()
    for row in rows:
        if row['trial_id'] in ids:
            raise ValueError('Duplicate trial ID')
        ids.add(row['trial_id'])
        if type(row.get('deterministic_pass')) is not bool:
            raise ValueError('Trial pass must be boolean')
        groups[row['task_id']].append(row)
    counts = {len(group) for group in groups.values()}
    if len(counts) > 1:
        raise ValueError('Repeated-task estimates require equal repeat counts')
    if len({row.get('backend') for row in rows}) > 1 or len({row.get('split') for row in rows}) > 1:
        raise ValueError('Do not pool backends or splits')
    n = next(iter(counts), 0)
    ks = list(ks) if ks is not None else list(range(1, n + 1))
    if any(type(k) is not int or not 1 <= k <= n for k in ks):
        raise ValueError('k must be an integer between 1 and repeats per task')
    repeated = {}
    for k in ks:
        scores = [sum(r['deterministic_pass'] for r in group) for group in groups.values()]
        repeated[str(k)] = {'pass_at_k': mean(1 - comb(n-c, k)/comb(n, k) for c in scores),
                            'pass_power_k': mean(comb(c, k)/comb(n, k) for c in scores)}
    def subset(predicate):
        selected = [r for r in rows if predicate(r)]
        passes = sum(r['deterministic_pass'] for r in selected)
        return {'trials': len(selected), 'passes': passes, 'pass_rate': passes/len(selected) if selected else None}
    confusion = defaultdict(Counter)
    for row in rows:
        confusion[str(row.get('expected_verdict'))][str(row.get('actual_verdict'))] += 1
    negatives = [r for r in rows if r.get('expected_verdict') == 'not_reproduced']
    fp = sum(r.get('actual_verdict') == 'confirmed' for r in negatives)
    latency = [r.get('elapsed_seconds') for r in rows]
    if any(type(x) not in (int, float) or not isfinite(x) or x < 0 for x in latency):
        raise ValueError('Latency must be finite nonnegative seconds')
    return {'repeated_trial_estimates': repeated, 'repeats_per_task': n,
            'estimator_note': 'Task-macro finite-sample estimators: 1-C(n-c,k)/C(n,k) and C(c,k)/C(n,k). Unbiased only for exchangeable independent repeats of a fixed task; not population generalization or a calibrated interval.',
            'denominators': {'all': subset(lambda r: True),
                'real_model_attempted': subset(lambda r: r.get('real_model_calls_attempted', 0) > 0),
                'real_model_completed': subset(lambda r: r.get('real_model_calls_completed', 0) > 0),
                'no_decision_calls': subset(lambda r: r.get('model_calls_attempted', 0) == 0),
                'no_call_refusal_controls': subset(lambda r: r.get('model_calls_attempted', 0) == 0 and r.get('expected_verdict') == 'inconclusive'),
                'full_exercise': subset(lambda r: r.get('requires_exercise') is True)},
            'verdict_confusion': {key: dict(value) for key, value in confusion.items()},
            'false_positives': {'confirmed_on_fixed': fp, 'fixed_trials': len(negatives), 'rate': fp/len(negatives) if negatives else None},
            'failure_taxonomy': dict(Counter(failure_category(r) for r in rows)),
            'latency_seconds': {'n': len(latency), 'mean': mean(latency) if latency else None,
                                'median': median(latency) if latency else None, 'max': max(latency) if latency else None}}
