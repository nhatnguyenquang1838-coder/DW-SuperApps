"""Materialize the additive, explicitly synthetic DWO work-demo pack.

Only writes DWO-WORK-DEMO-V1. Does not modify the sealed DWO-UR-30-V1 pack.
All story outcomes are fictional UI data, never execution/qualification proof.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

PACK_ID = 'DWO-WORK-DEMO-V1'
ROOT = Path(__file__).resolve().parents[1] / 'dwo-v2' / 'fixtures' / PACK_ID


def dump(relative, value, lines=False):
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    text = '\n'.join(json.dumps(v, sort_keys=True) for v in value) if lines else json.dumps(value, indent=2, sort_keys=True)
    path.write_text(text + '\n', encoding='utf-8')


def history(run_id, outcome, purpose, offset):
    rows = []
    def add(gate, state, event_type, summary, *, run_state='OPEN', authority='NOT_REQUIRED'):
        sequence = len(rows)
        stamp = (datetime(2026, 9, 1, tzinfo=timezone.utc) + timedelta(minutes=offset + sequence)).isoformat().replace('+00:00', 'Z')
        event_id = f'{run_id}-EVENT-{sequence:03d}'
        rows.append(dict(event_id=event_id, source_event_id=event_id,
            source_system=f'fixture://{PACK_ID}/{run_id}', run_id=run_id,
            ordinal=offset + sequence, sequence=sequence,
            created_at=stamp, occurred_at=stamp, created_by=f'fixture://{PACK_ID}/generator',
            actor='synthetic-demo-executor', synthetic=True, event_type=event_type,
            node_id=run_id, gate=gate, gate_state=state, run_state=run_state,
            source_profile='DEV_NATIVE', sync_state='LIVE', semantic_qualification='PENDING',
            authority_state=authority, anomaly_count=0, summary=summary,
            outcome=state.lower(), evidence_refs=[]))
    for gate, active, passed in [('G0', 'Understand work and constraints', 'Scope understood'),
                                  ('G1', 'Plan tasks and dependencies', 'Plan recorded')]:
        add(gate, 'ACTIVE', 'run_started' if gate == 'G0' else 'node_progress', active)
        add(gate, 'PASSED', 'gate_passed', passed)
    add('G2', 'ACTIVE', 'node_started', f'Implement: {purpose}')
    if outcome == 'blocked':
        add('G2', 'WAITING', 'node_progress', 'Request prerequisite integration and synthetic authorization', authority='PENDING')
        add('G2', 'BLOCKED', 'node_progress', 'Waiting on prerequisite API contract and denied demo authority', authority='DENIED')
    else:
        add('G2', 'PASSED', 'node_completed', 'Implementation artifact ready')
        add('G3', 'ACTIVE', 'node_progress', 'Run verification checks')
        if outcome == 'retry':
            add('G3', 'FAILED', 'gate_failed', 'Verification failed: empty-state assertion')
            add('G2', 'ACTIVE', 'node_started', 'Retry execution after verification failure')
            add('G2', 'PASSED', 'node_completed', 'Repair empty-state rendering')
            add('G3', 'ACTIVE', 'node_progress', 'Recheck repaired artifact; not yet accepted')
        else:
            add('G3', 'PASSED', 'gate_passed', 'Verification checks passed in this fictional story')
            for gate, active, passed in [('G4', 'Integrate into local demo target', 'Target integration recorded'),
                                         ('G5', 'Validate integrated demo target', 'Target validation recorded'),
                                         ('G6', 'Prepare acceptance and handoff', 'Demo work accepted with handoff')]:
                add(gate, 'ACTIVE', 'node_progress', active)
                add(gate, 'PASSED', 'gate_passed', passed, run_state='ACCEPTED' if gate == 'G6' else 'OPEN')
    rows[-1]['evidence_refs'] = [f'execution/{run_id}-execution.json', f'verification/{run_id}-verification.json']
    return rows


def main():
    catalog, events, tasks, metas = [], [], [], []
    stories = [
        ('DELIVERY', 'accepted', 'Completed delivery: API and dashboard', [
            ('API', 'accepted', 'Implement the task-summary API with explicit unavailable responses'),
            ('UI', 'accepted', 'Render dashboard summary and empty states')]),
        ('BLOCKED', 'blocked', 'Blocked work: dependency and denied authority', [
            ('API', 'accepted', 'Prepare versioned prerequisite API contract'),
            ('UI', 'blocked', 'Integrate UI only after contract and demo authorization')]),
        ('RETRY', 'retry', 'Verification failure and repair in progress', [
            ('API', 'accepted', 'Provide deterministic task data for verification'),
            ('UI', 'retry', 'Repair empty-state assertion and rerun checks')]),
    ]
    for story_index, (story, outcome, title, children) in enumerate(stories):
        root_id = f'DEMO-{story}-ROOT'
        task_ref = f'DEMO-TASK-{story}'
        definitions: list[tuple[str, str, str, str | None, list[str]]] = [(f'DEMO-{story}-{suffix}', child_outcome, purpose, root_id, []) for suffix, child_outcome, purpose in children]
        definitions.append((root_id, outcome, title, None, [d[0] for d in definitions]))
        for run_id, run_outcome, purpose, parent, child_ids in definitions:
            stream = history(run_id, run_outcome, purpose, len(catalog) * 100)
            tip = stream[-1]
            catalog.append(dict(id=run_id, domain='SOFTWARE/DEMO', kind='ROOT' if parent is None else 'ATOMIC',
                parent=parent, gate=tip['gate'], gateState=tip['gate_state'], runState=tip['run_state'],
                sourceProfile=tip['source_profile'], syncState=tip['sync_state'], semanticQualification='PENDING',
                authorityState=tip['authority_state'], anomalyCount=0, purpose=purpose,
                children=child_ids, deps=[f'DEMO-{story}-API'] if run_id.endswith('-UI') or parent is None else []))
            events.extend(stream)
            common = dict(run_id=run_id, synthetic=True, fixture_set=PACK_ID,
                          notice='Fictional work story for UI review. Not real execution, approval, qualification or deployment evidence.')
            dump(f'evidence/execution/{run_id}-execution.json', dict(common,
                objective=purpose, task_ref=task_ref, result=run_outcome,
                steps=[dict(event_id=e['event_id'], gate=e['gate'], state=e['gate_state'], summary=e['summary']) for e in stream],
                artifacts=[dict(path=f'demo/{story.lower()}/{run_id.lower()}.txt', content=f'Synthetic work artifact: {purpose}')],
                blocked_reason='Prerequisite contract integration and demo authority are unresolved' if run_outcome == 'blocked' else None))
            dump(f'evidence/verification/{run_id}-verification.json', dict(common,
                result='PASSED' if run_outcome == 'accepted' else 'PENDING' if run_outcome == 'retry' else 'NOT_RUN',
                checks=[dict(name='task summary renders', result='PASS' if run_outcome == 'accepted' else 'PENDING'),
                        dict(name='empty state is explicit', result='PASS' if run_outcome == 'accepted' else 'FAILED_THEN_RETRY_PENDING' if run_outcome == 'retry' else 'NOT_RUN')],
                attempts=2 if run_outcome == 'retry' else 1))
            if run_outcome == 'accepted':
                dump(f'evidence/handoff/{run_id}-handoff.json', dict(common,
                    result='ACCEPTED_IN_SYNTHETIC_STORY', open_items=[], target='local fictional demo only'))
        relation = dict(taskRef=task_ref, relationRevisionId='rel-1', rootRunIds=[root_id],
                        sourceSystem='DWO_WORK_DEMO', sourceRecordId=f'{task_ref}-rel-1',
                        durablePosition=story_index + 1, supersedesRevisionId=None)
        relation['sourceDigest'] = 'sha256:' + hashlib.sha256(json.dumps(relation, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        tasks.append(relation)
        metas.append(dict(taskRef=task_ref, title=title, domain='SOFTWARE/DEMO', runCount=1))
    dump('catalog.json', catalog)
    dump('events/projection-events.jsonl', events, lines=True)
    dump('tasks/task-relations.jsonl', tasks, lines=True)
    dump('tasks/metadata.json', metas)
    dump('manifest.json', dict(fixture_set=PACK_ID, synthetic=True, runs=len(catalog), tasks=len(tasks), events=len(events),
                               qualification='NOT_CERTIFIED', capabilities=dict(read=True, write=False, approve=False, merge=False, deploy=False)))
    print(json.dumps(dict(pack=PACK_ID, runs=len(catalog), tasks=len(tasks), events=len(events), evidence_files=len(list((ROOT / 'evidence').rglob('*.json'))))))


if __name__ == '__main__':
    main()
