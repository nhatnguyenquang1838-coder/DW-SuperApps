import { act, createElement, type ReactNode } from 'react';
import { hydrateRoot, type Root } from 'react-dom/client';
import { renderToString } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import '@testing-library/jest-dom';

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
import RuntimeGraphCanvas from '@/components/dwo/RuntimeGraphCanvas';
import { computeRuntimeGraphLayout } from '@/components/dwo/graphLayout';
import { FIXTURE_CATALOG } from '@/lib/dwo/fixtureSpec';
import { materializeFixtureScenario } from '@/lib/dwo/materializeFixtureScenario';

vi.mock('@xyflow/react', async () => {
  const React = await import('react');
  return {
    ReactFlow: ({ nodes, children }: { nodes: Array<{ id: string; type?: string; position: { x: number; y: number } }>; children?: ReactNode }) =>
      React.createElement('div', { 'data-testid': 'mock-flow' },
        ...nodes.map((node) => React.createElement('i', {
          key: node.id,
          'data-node-id': node.type === 'runtimeNode' ? node.id : undefined,
          'data-x': node.position.x,
          'data-y': node.position.y,
        })),
        children,
      ),
    Background: () => null,
    Controls: () => null,
    MarkerType: { ArrowClosed: 'arrowclosed' },
    useReactFlow: () => ({ fitView: vi.fn(), setCenter: vi.fn(), zoomIn: vi.fn(), zoomOut: vi.fn(), setViewport: vi.fn() }),
    useNodesInitialized: () => true,
  };
});

const model = materializeFixtureScenario(FIXTURE_CATALOG.find((row) => row.id === 'DEV-RUN-024')!);
const props = {
  model,
  cursor: 0,
  selection: { kind: 'run' as const, id: 'DEV-RUN-024' },
  followCursor: false,
  onSelectNode: vi.fn(),
  onOpenArtifact: vi.fn(),
  onUserViewportInteract: vi.fn(),
};
const mountedRoots: Root[] = [];

afterEach(() => {
  for (const root of mountedRoots.splice(0)) act(() => root.unmount());
  window.history.replaceState({}, '', '/');
});

function button(container: ParentNode, id: string): HTMLButtonElement {
  const element = container.querySelector(`[data-testid="${id}"]`);
  if (!(element instanceof HTMLButtonElement)) throw new Error(`Missing button ${id}`);
  return element;
}

function setSearch(search: string) {
  window.history.replaceState({}, '', `/runs/DEV-RUN-024${search}`);
}

describe('R3-03 SSR-safe layout deep links', () => {
  it('hydrates a TD/Stack deep link without mismatches and renders matching controls and geometry', async () => {
    setSearch('?dir=TD&form=stack');
    const originalWindow = globalThis.window;
    let html: string;
    Object.defineProperty(globalThis, 'window', { configurable: true, value: undefined });
    try {
      html = renderToString(createElement(RuntimeGraphCanvas, props));
    } finally {
      Object.defineProperty(globalThis, 'window', { configurable: true, value: originalWindow });
    }

    const host = document.createElement('div');
    host.innerHTML = html;
    document.body.append(host);
    const errors: unknown[][] = [];
    const consoleError = vi.spyOn(console, 'error').mockImplementation((...args) => errors.push(args));
    let root: Root;
    try {
      await act(async () => {
        root = hydrateRoot(host, createElement(RuntimeGraphCanvas, props), {
          onRecoverableError: (...args) => errors.push(args),
        });
        mountedRoots.push(root);
      });
      expect(button(host, 'layout-td')).toHaveAttribute('aria-pressed', 'true');
      expect(button(host, 'layout-td')).toHaveClass('on');
      expect(button(host, 'layout-lr')).toHaveAttribute('aria-pressed', 'false');
      expect(button(host, 'layout-stack')).toHaveAttribute('aria-pressed', 'true');
      expect(button(host, 'layout-stack')).toHaveClass('on');
      expect(button(host, 'layout-grid')).toHaveAttribute('aria-pressed', 'false');
      const expected = computeRuntimeGraphLayout(model.nodes, { direction: 'TD', form: 'stack', grouped: true });
      const sample = model.nodes[0];
      const renderedNode = host.querySelector(`[data-node-id="${sample.id}"]`);
      expect(renderedNode).not.toBeNull();
      expect(Number(renderedNode?.getAttribute('data-x'))).toBe(expected.nodes[sample.id].x);
      expect(Number(renderedNode?.getAttribute('data-y'))).toBe(expected.nodes[sample.id].y);
      expect(host.querySelectorAll('[data-node-id]')).toHaveLength(model.nodes.length);
      expect(errors).toEqual([]);
    } finally {
      consoleError.mockRestore();
      host.remove();
    }
  });

  it('uses LR/Grid for missing or unsupported query values, then preserves manual layout changes', async () => {
    const host = document.createElement('div');
    setSearch('');
    host.innerHTML = renderToString(createElement(RuntimeGraphCanvas, props));
    expect(button(host, 'layout-lr')).toHaveAttribute('aria-pressed', 'true');
    expect(button(host, 'layout-grid')).toHaveAttribute('aria-pressed', 'true');
    setSearch('?dir=sideways&form=unknown');
    document.body.append(host);
    const errors: unknown[][] = [];
    const consoleError = vi.spyOn(console, 'error').mockImplementation((...args) => errors.push(args));
    let root: Root | undefined;
    try {
      await act(async () => {
        root = hydrateRoot(host, createElement(RuntimeGraphCanvas, props), {
          onRecoverableError: (...args) => errors.push(args),
        });
        mountedRoots.push(root);
      });
      expect(button(host, 'layout-lr')).toHaveAttribute('aria-pressed', 'true');
      expect(button(host, 'layout-grid')).toHaveAttribute('aria-pressed', 'true');
      await act(async () => {
        button(host, 'layout-td').click();
        button(host, 'layout-stack').click();
      });
      expect(button(host, 'layout-td')).toHaveAttribute('aria-pressed', 'true');
      expect(button(host, 'layout-stack')).toHaveAttribute('aria-pressed', 'true');
      expect(errors).toEqual([]);
    } finally {
      consoleError.mockRestore();
      host.remove();
    }
  });
});
