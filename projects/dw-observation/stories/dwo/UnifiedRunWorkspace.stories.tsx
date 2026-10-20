import type { Meta, StoryObj } from "@storybook/react";
import UnifiedRunWorkspace from "@/components/dwo/UnifiedRunWorkspace";
import { SCENARIOS, makeModel } from "./fixtures";

const meta: Meta<typeof UnifiedRunWorkspace> = {
  title: "DWO/UnifiedRunWorkspace",
  component: UnifiedRunWorkspace,
  tags: ["autodocs"],
};
export default meta;

type Story = StoryObj<typeof UnifiedRunWorkspace>;

// SCENARIOS holds Partial models (scenario deltas). Each story needs the FULL
// UnifiedRunWorkspaceModel, so spread the delta over makeModel() rather than
// casting with `as any` — the cast silenced exactly the prop-shape drift this
// task is meant to catch.
const withDefaults = (delta: Partial<Parameters<typeof makeModel>[0]>) => makeModel(delta);

export const LoginAuthSimulated: Story = { args: { model: withDefaults(SCENARIOS.LoginAuthSimulated) } };
export const NodeArchitectSimulated: Story = { args: { model: withDefaults(SCENARIOS.NodeArchitectSimulated) } };
export const LiveReal: Story = { args: { model: withDefaults(SCENARIOS.LiveReal) } };
export const Replay: Story = { args: { model: withDefaults(SCENARIOS.Replay) } };
export const Degraded: Story = { args: { model: withDefaults(SCENARIOS.Degraded) } };
export const RelationConflict: Story = { args: { model: withDefaults(SCENARIOS.RelationConflict) } };