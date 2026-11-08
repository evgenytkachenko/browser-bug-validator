"""Fail closed unless the complete development scripted browser control passed."""
import argparse
import json

from evaluations.general_integrity import load_general_run
from evaluations.general_tasks import TASKS


def validate_control(manifest, rows):
    """Apply CI policy after the integrity loader has replayed objective grades."""
    def require(condition, message):
        if not condition:
            raise ValueError(message)

    tasks = [task for task in TASKS if task['split'] == 'development']
    require(manifest.get('completed') is True, 'Run is incomplete')
    require(manifest.get('backend') == 'scripted-control', 'Not a scripted control')
    require(manifest.get('split') == 'development', 'Only development cases belong in this CI job')
    require(manifest.get('task_ids') == [task['id'] for task in tasks], 'Incomplete development task selection')
    require(manifest.get('trials_per_task') == 1, 'CI expects one trial per development task')
    require(manifest.get('source_frozen_through_run') is True, 'Sources changed during execution')
    require(manifest.get('model_quality_claim_eligible') is False, 'Scripted control is not a model-quality result')
    require(set(rows) == {f"{task['id']}--001" for task in tasks}, 'Incomplete trial schedule')
    for task in tasks:
        row = rows[f"{task['id']}--001"]
        require(row.get('deterministic_pass') is True, task['id'] + ': objective checks failed')
        require(row.get('real_model_calls_attempted') == 0 and row.get('real_model_calls_completed') == 0,
                task['id'] + ': unexpected real-model activity')
        browser_expected = not (task.get('deny_mutation') or task.get('omit_requirement'))
        require(row.get('browser_started') is browser_expected, task['id'] + ': browser participation mismatch')
        if task['expected_verdict'] != 'inconclusive':
            require(row.get('browser_observations', 0) > 0, task['id'] + ': no actual browser evidence')
    return {'passed': True, 'trials': len(rows), 'real_browser_trials': sum(r['browser_started'] for r in rows.values()),
            'real_model_calls': 0, 'reserved_executed': 0,
            'measurement_kind': 'scripted-policy-real-browser-integration-control',
            'model_quality_claim': False, 'semantic_status': 'unverified'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory')
    args = parser.parse_args()
    manifest, rows = load_general_run(args.directory)
    print(json.dumps(validate_control(manifest, rows), sort_keys=True))


if __name__ == '__main__':
    main()
