import { describe, it, expect } from 'vitest';
import { computeRuntimeGraphLayout } from '@/components/dwo/graphLayout';
const nodes=[{id:'A',gateId:'G1',title:'A'},{id:'B',gateId:'G2',title:'B'}];
describe('R2 stack direction contract',()=>{
 it('stacks groups vertically for TD and horizontally for LR',()=>{
  const td=computeRuntimeGraphLayout(nodes,{direction:'TD',form:'stack',grouped:true});
  expect(td.groups[1].x).toBe(td.groups[0].x);
  expect(td.groups[1].y).toBeGreaterThan(td.groups[0].y+td.groups[0].height);
  const lr=computeRuntimeGraphLayout(nodes,{direction:'LR',form:'stack',grouped:true});
  expect(lr.groups[1].y).toBe(lr.groups[0].y);
  expect(lr.groups[1].x).toBeGreaterThan(lr.groups[0].x+lr.groups[0].width);
 });
});
