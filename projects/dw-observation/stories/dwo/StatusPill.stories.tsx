import type { Meta, StoryObj } from "@storybook/react";
import StatusPill from "@/components/dwo/StatusPill";

const meta: Meta<typeof StatusPill> = {
  title: "DWO/StatusPill",
  component: StatusPill,
  tags: ["autodocs"],
  argTypes: {
    status: {
      control: "select",
      options: ["RESOLVED", "UNKNOWN_UNRESOLVED", "CONFLICT", "UNAVAILABLE", "ACTIVE", "WAITING", "BLOCKED", "COMPLETED", "DEGRADED"],
    },
  },
};
export default meta;

type Story = StoryObj<typeof StatusPill>;

export const RESOLVED: Story = { args: { status: "RESOLVED" } };
export const UNKNOWN_UNRESOLVED: Story = { args: { status: "UNKNOWN_UNRESOLVED" } };
export const CONFLICT: Story = { args: { status: "CONFLICT" } };
export const UNAVAILABLE: Story = { args: { status: "UNAVAILABLE" } };
export const ACTIVE: Story = { args: { status: "ACTIVE" } };
export const WAITING: Story = { args: { status: "WAITING" } };
export const BLOCKED: Story = { args: { status: "BLOCKED" } };
export const COMPLETED: Story = { args: { status: "COMPLETED" } };
export const DEGRADED: Story = { args: { status: "DEGRADED" } };