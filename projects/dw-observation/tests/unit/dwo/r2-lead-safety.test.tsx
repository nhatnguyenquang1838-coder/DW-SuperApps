import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { mkdtempSync, mkdirSync, writeFileSync, symlinkSync, rmSync } from 'node:fs';
import path from 'node:path';
import { readFixtureEvidence } from '@/lib/dwo/fixtureEvidenceRead';
import { GET } from '@/app/dev/evidence/[runId]/route';
import ArtifactViewer from '@/components/dwo/ArtifactViewer';
const roots:string[]=[];
const env={NODE_ENV:'test',OBSERVATORY_DATA_SOURCE:'fixture'};
afterEach(()=>{vi.restoreAllMocks();vi.unstubAllGlobals();vi.unstubAllEnvs();for(const p of roots.splice(0))rmSync(p,{recursive:true,force:true});});
function root(){const p=mkdtempSync(path.join(process.env.TMPDIR??'D:/HermesData/cache/scratch','r2-safe-'));roots.push(p);return p;}
function file(base:string,record:object){const dir=path.join(base,'dwo-v2/fixtures/DWO-UR-30-V1/evidence/execution');mkdirSync(dir,{recursive:true});writeFileSync(path.join(dir,'DEV-RUN-024-execution.json'),JSON.stringify(record));}
describe('Lead R2 security and interaction corrections',()=>{
 it('accepts the normal single-encoded evidence query used by its own viewer',async()=>{
  vi.stubEnv('OBSERVATORY_DATA_SOURCE','fixture');
  const r=await GET(new Request('http://localhost/dev/evidence/DEV-RUN-024?path=execution%2FDEV-RUN-024-execution.json'),{params:{runId:'DEV-RUN-024'}});
  expect(r.status).toBe(200);expect(await r.text()).toContain('DEV-RUN-024-ExecutionReceipt');
 });
 it('rejects contradictory run association fields',()=>{const cwd=root();file(cwd,{run_id:'DEV-RUN-025',dwo_run_id:'DEV-RUN-024'});vi.spyOn(process,'cwd').mockReturnValue(cwd);expect(readFixtureEvidence('DEV-RUN-024','execution/DEV-RUN-024-execution.json',env).ok).toBe(false);});
 it('does not trust an evidence-root junction outside the fixture tree',()=>{const cwd=root(),outside=root();file(outside,{run_id:'DEV-RUN-024'});const parent=path.join(cwd,'dwo-v2/fixtures/DWO-UR-30-V1');mkdirSync(parent,{recursive:true});symlinkSync(path.join(outside,'dwo-v2/fixtures/DWO-UR-30-V1/evidence'),path.join(parent,'evidence'),'junction');vi.spyOn(process,'cwd').mockReturnValue(cwd);expect(readFixtureEvidence('DEV-RUN-024','execution/DEV-RUN-024-execution.json',env).ok).toBe(false);});
 it('denies production and unselected source mode',()=>{for(const denied of [{NODE_ENV:'production',OBSERVATORY_DATA_SOURCE:'fixture'},{NODE_ENV:'test',OBSERVATORY_DATA_SOURCE:'real'}])expect(readFixtureEvidence('DEV-RUN-024','execution/DEV-RUN-024-execution.json',denied)).toMatchObject({ok:false,status:404});});
 it('rejects oversized and non-object JSON evidence',()=>{const cwd=root();file(cwd,{run_id:'DEV-RUN-024',payload:'x'.repeat(128*1024)});vi.spyOn(process,'cwd').mockReturnValue(cwd);expect(readFixtureEvidence('DEV-RUN-024','execution/DEV-RUN-024-execution.json',env)).toMatchObject({ok:false,status:413});writeFileSync(path.join(cwd,'dwo-v2/fixtures/DWO-UR-30-V1/evidence/execution/DEV-RUN-024-execution.json'),'[]');expect(readFixtureEvidence('DEV-RUN-024','execution/DEV-RUN-024-execution.json',env)).toMatchObject({ok:false,status:400});});
 it('places keyboard focus inside the artifact modal',async()=>{vi.stubGlobal('fetch',vi.fn().mockResolvedValue({json:async()=>({ok:true,text:'{"run_id":"DEV-RUN-024"}',runId:'DEV-RUN-024',path:'execution/DEV-RUN-024-execution.json',bytes:24})}));render(<ArtifactViewer runId="DEV-RUN-024" path="execution/DEV-RUN-024-execution.json" onClose={()=>{}}/>);await screen.findByText(/no qualification or authority/);expect(screen.getByRole('button',{name:'Close artifact viewer'})).toHaveFocus();});
});
