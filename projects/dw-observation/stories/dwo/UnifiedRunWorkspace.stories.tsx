import type { Meta, StoryObj } from "@storybook/react";
import UnifiedRunWorkspace from "@/components/dwo/UnifiedRunWorkspace";
import { SCENARIOS } from "./fixtures";

const meta: Meta<typeof UnifiedRunWorkspace> = {
  title: "DWO/UnifiedRunWorkspace",
  component: UnifiedRunWorkspace,
  tags: ["autodocs"],
};
export default meta;

type Story = StoryObj<typeof UnifiedRunWorkspace>;

export const LoginAuthSimulated: Story = { args: { model: SCENARIOS.LoginAuthSimulated as any } };
export const NodeArchitectSimulated: Story = { args: { model: SCENARIOS.NodeArchitectSimulated as any } };
export const LiveReal: Story = { args: { model: SCENARIOS.LiveReal as any } };
export const Replay: Story = { args: { model: SCENARIOS.Replay as any } };
export const Degraded: Story = { args: { model: SCENARIOS.Degraded as any } };
export const RelationConflict: Story = { args: { model: SCENARIOS.RelationConflict as any } };