"""Add a recursive, interleaved synthetic story to the work-demo generator.

All lifecycle facts below are authored fixture data, not real execution evidence.
The global ordinal is fixture order; source sequence stays per run.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json


def append_recursive_story(catalog, events, tasks, metas, history, dump):
    root = 'DEMO-RECURSIVE-ROOT'
    child = 'DEMO-RECURSIVE-CHILD'
    api = 'DEMO-RECURSIVE-API'
    ui = 'DEMO-RECURSIVE-UI'
    task = 'DEMO-TASK-RECURSIVE'
    definitions = [
        (root, 'ROOT', None, [child], [], 'Deliver a task workspace through a delegated child run'),
        (child, 'CHILD', root, [api, ui], [], 'Compose API and UI atomic work, verify and hand back to root'),
        (api, 'ATOMIC', child, [], [], 'Implement the task-summary API'),
        (ui, 'ATOMIC', child, [], [api], 'Implement the UI against the accepted API contract'),
    ]
    streams = {run_id: history(run_id, 'accepted', purpose, 0) for run_id, _, _, _, _, purpose in definitions}
    ordered = []
    def begin_parent(run_id, summary):
        ordered.extend(streams[run_id][:5])
        ordered.append(dict(streams[run_id][4], gate_state='WAITING', event_type='node_progress', outcome='waiting', summary=summary))
    def finish_parent(run_id, summary):
        ordered.append(dict(streams[run_id][4], summary=summary))
        ordered.extend(streams[run_id][5:])
    begin_parent(root, 'Root waits for its delegated CHILD; no implicit completion')
    begin_parent(child, 'Child waits for both ATOMIC runs; no implicit completion')
    ordered.extend(streams[api])
    ordered.extend(streams[ui])
    milestones = {'atomicDone': len(ordered)}
    finish_parent(child, 'Child resumes after both atomics; composition still needs its own G3–G6')
    milestones['childDone'] = len(ordered)
    finish_parent(root, 'Root resumes after child acceptance; root still needs its own G3–G6')
    milestones['accepted'] = len(ordered)
    sequences = {run_id: 0 for run_id in streams}
    for index, event in enumerate(ordered):
        run_id = event['run_id']
        sequence = sequences[run_id]
        sequences[run_id] += 1
        event_id = f'{run_id}-EVENT-{sequence:03d}'
        stamp = (datetime(2026, 9, 2, tzinfo=timezone.utc) + timedelta(minutes=index)).isoformat().replace('+00:00', 'Z')
        event.update(event_id=event_id, source_event_id=event_id, sequence=sequence,
                     ordinal=1000 + index, created_at=stamp, occurred_at=stamp)
    events.extend(ordered)
    for run_id, kind, parent, children, deps, purpose in definitions:
        stream = [event for event in ordered if event['run_id'] == run_id]
        tip = stream[-1]
        catalog.append(dict(id=run_id, domain='SOFTWARE/RECURSIVE_DEMO', kind=kind, parent=parent,
            gate=tip['gate'], gateState=tip['gate_state'], runState=tip['run_state'], sourceProfile='DEV_NATIVE',
            syncState='LIVE', semanticQualification='PENDING', authorityState='NOT_REQUIRED', anomalyCount=0,
            purpose=purpose, children=children, deps=deps, declaredGates=['G0', 'G1', 'G2', 'G3', 'G4', 'G5', 'G6']))
        common = dict(run_id=run_id, synthetic=True, fixture_set='DWO-WORK-DEMO-V1',
            notice='Fictional recursive workflow. Not real execution, qualification, approval, merge or deployment evidence.')
        dump(f'evidence/execution/{run_id}-execution.json', dict(common, task_ref=task, objective=purpose,
            steps=[dict(event_id=e['event_id'], gate=e['gate'], state=e['gate_state'], summary=e['summary']) for e in stream]))
        dump(f'evidence/verification/{run_id}-verification.json', dict(common, result='PASSED_IN_SYNTHETIC_STORY',
            checks=[dict(name='explicit G0–G6 history', result='PASS_IN_SYNTHETIC_STORY'),
                    dict(name='parent has independent completion', result='PASS_IN_SYNTHETIC_STORY')]))
        dump(f'evidence/handoff/{run_id}-handoff.json', dict(common, result='ACCEPTED_IN_SYNTHETIC_STORY',
            target='local fictional demo only', open_items=[]))
    relation = dict(taskRef=task, relationRevisionId='rel-1', rootRunIds=[root], sourceSystem='DWO_WORK_DEMO',
                    sourceRecordId=f'{task}-rel-1', durablePosition=4, supersedesRevisionId=None)
    relation['sourceDigest'] = 'sha256:' + hashlib.sha256(json.dumps(relation, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    tasks.append(relation)
    metas.append(dict(taskRef=task, title='Recursive G0–G6: ROOT → CHILD → ATOMIC', domain='SOFTWARE/RECURSIVE_DEMO', runCount=1))
    dump('recursive-scenario.json', dict(rootRunId=root, taskRef=task, runIds=list(streams),
        eventCount=len(ordered), milestones=milestones, synthetic=True,
        initialPrefixCursor=1, notice='Declared topology; node/gate state follows the selected event prefix.'))
