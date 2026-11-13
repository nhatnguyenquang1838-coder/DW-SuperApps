import Link from 'next/link';
import { WORK_DEMO_CATALOG, WORK_DEMO_PACK } from '@/lib/dwo/fixturePreviewCatalog';
import { createFixtureReplaySession } from '@/lib/dwo/fixtureReplaySession';
import manifest from '@/dwo-v2/fixtures/DWO-WORK-DEMO-V1/manifest.json';

/** Discoverable story entry points; all detail/replay stays in the normal shell. */
export default function FixtureWorkShowcase() {
  const roots = WORK_DEMO_CATALOG.filter(run => run.parent === null);
  return <section className="my-6 space-y-3" aria-label="Work demo scenarios" data-testid="work-demo-showcase">
    <h2 className="text-xl font-semibold">Explore work in progress</h2>
    <p className="text-sm" style={{ color: 'var(--dwo-color-text-muted)' }}>
      {WORK_DEMO_PACK} · {manifest.runs} runs · {manifest.events} recorded demo events.
      Synthetic stories for inspection—not real execution, authority or qualification.
    </p>
    <div className="grid gap-3 sm:grid-cols-3">
      {roots.map(run => <article key={run.id} className="min-w-0 rounded border p-4 space-y-3" style={{ borderColor: 'var(--dwo-color-border-default)', background: 'var(--dwo-color-bg-subtle)' }}>
        <h3 className="font-semibold">{run.purpose}</h3>
        <p className="text-sm break-words">{run.gate} · {run.gateState} · {run.runState}</p>
        <p className="text-xs" style={{ color: 'var(--dwo-color-text-muted)' }}>{run.children.length} child runs · {createFixtureReplaySession(run.id)?.total ?? 'unavailable'} root events · authority: {run.authorityState}</p>
        <div className="flex flex-wrap gap-3 text-sm">
          <Link className="underline" href={`/runs/${run.id}`}>Inspect work</Link>
          <Link className="underline" href={`/runs/${run.id}/replay`}>Replay history</Link>
        </div>
      </article>)}
    </div>
  </section>;
}
