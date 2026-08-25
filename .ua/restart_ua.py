#!/usr/bin/env python3
"""
Restart UA refresh pipeline for DW-SuperApps from checkpoints.
"""

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime

def check_state():
    """Check current UA state"""
    meta_path = Path('/Users/mac/prj/DW-SuperApps/.ua/meta.json')
    kg_path = Path('/Users/mac/prj/DW-SuperApps/.ua/knowledge-graph.json')
    
    state = {
        'meta': None,
        'kg_exists': kg_path.exists(),
        'meta_timestamp': None,
        'analyzed_files': 0,
    }
    
    if meta_path.exists():
        with open(meta_path) as f:
            state['meta'] = json.load(f)
            state['meta_timestamp'] = state['meta'].get('lastAnalyzedAt')
            state['analyzed_files'] = state['meta'].get('analyzedFiles', 0)
    
    return state

def restart_ua_refresh():
    """Restart UA refresh process"""
    print("Checking current state...")
    state = check_state()
    print(f"Current state: {state['meta_timestamp']}, {state['analyzed_files']} files analyzed")
    print(f"Knowledge graph exists: {state['kg_exists']}")
    
    # Check if there are intermediate files (checkpoints)
    intermediate_path = Path('/Users/mac/prj/DW-SuperApps/.ua/intermediate')
    if intermediate_path.exists():
        intermediate_files = list(intermediate_path.glob('*'))
        print(f"Intermediate files: {len(intermediate_files)}")
        for f in intermediate_files[:5]:
            print(f"  - {f.name}")
    
    # Check tmp directory
    tmp_path = Path('/Users/mac/prj/DW-SuperApps/.ua/tmp')
    if tmp_path.exists():
        tmp_files = list(tmp_path.glob('*'))
        print(f"Temp files: {len(tmp_files)}")
        for f in tmp_files[:5]:
            print(f"  - {f.name}")
    
    print("\nTo restart UA refresh, run:")
    print("  cd /Users/mac/prj/DW-SuperApps")
    print("  /usr/bin/python3 -c \"from hermes_tools import terminal; terminal('cd DW-SuperApps && /usr/bin/python3 -m node-analyzer --project .')\"")
    
    return state

if __name__ == '__main__':
    restart_ua_refresh()