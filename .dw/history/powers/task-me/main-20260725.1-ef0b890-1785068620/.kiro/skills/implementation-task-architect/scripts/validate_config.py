#!/usr/bin/env python3
from __future__ import annotations
import json, sys
from pathlib import Path

def main():
    root=Path.cwd().resolve(); path=root/'.task-architect/config.json'
    try: cfg=json.loads(path.read_text(encoding='utf-8'))
    except Exception as e: print(f'ERROR config: {e}'); return 2
    errors=[]
    if cfg.get('output',{}).get('folder_mode')!='per_task': errors.append('output.folder_mode must be per_task')
    pattern=cfg.get('output',{}).get('task_folder_pattern','')
    if '{task_id}' not in pattern or '{slug}' not in pattern: errors.append('task_folder_pattern must contain {task_id} and {slug}')
    out=(root/cfg.get('output',{}).get('root','')).resolve()
    try: out.relative_to(root)
    except ValueError: errors.append('output.root must remain inside repository')
    if cfg.get('knowledge',{}).get('root')!='.ua': errors.append('knowledge.root must be .ua')
    for e in errors: print('ERROR',e)
    if errors: return 2
    print('CONFIG_VALID'); return 0
if __name__=='__main__': sys.exit(main())
