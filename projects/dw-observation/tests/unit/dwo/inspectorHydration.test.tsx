import React from 'react';
import { expect, it, vi } from 'vitest';
import { renderToString } from 'react-dom/server';
import { render, screen, fireEvent } from '@testing-library/react';
import NodeInspector from '@/components/dwo/NodeInspector';
import { materializeFixtureScenario } from '@/lib/dwo/materializeFixtureScenario';
import { PREVIEW_FIXTURE_CATALOG } from '@/lib/dwo/fixturePreviewCatalog';

it('inspector tabs cannot accept a lost click before hydration, then become interactive', () => {
  const model = materializeFixtureScenario(PREVIEW_FIXTURE_CATALOG.find(r => r.id === 'DEMO-DELIVERY-ROOT')!);
  const changed = vi.fn();
  const props = { node: model.nodes[0], activeTab: 'overview' as const, onTabChange: changed };
  const html = renderToString(<NodeInspector {...props} />);
  expect(html).toMatch(/data-tab="artifacts"[^>]*disabled=""/);
  render(<NodeInspector {...props} />);
  const tab = screen.getByRole('button', { name: /^Artifacts$/ });
  expect((tab as HTMLButtonElement).disabled).toBe(false);
  fireEvent.click(tab);
  expect(changed).toHaveBeenCalledWith('artifacts');
});
