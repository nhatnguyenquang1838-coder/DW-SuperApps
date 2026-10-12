import type { Meta, StoryObj } from "@storybook/react";
import Dashboard from "@/components/dwo/Dashboard";
import { readDashboardProjection } from "@/lib/dashboard/readDashboardProjection";

const meta: Meta<typeof Dashboard> = {
  title: "DWO/Dashboard",
  component: Dashboard,
  tags: ["autodocs"],
};
export default meta;

type Story = StoryObj<typeof Dashboard>;

export const healthy: Story = {
  args: { projection: readDashboardProjection("fixture", []) },
};
export const attention: Story = {
  args: { projection: readDashboardProjection("fixture", [{ taskRef: "SCRUM-820", relationRevisionId: "r1", rootRunIds: ["R1"], sourceSystem: "DWO", sourceRecordId: "r1", sourceDigest: "d1", durablePosition: 1, supersedesRevisionId: null }]) },
};
export const degraded: Story = {
  args: { projection: readDashboardProjection("fixture", []) },
};