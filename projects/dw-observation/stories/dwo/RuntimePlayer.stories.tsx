import type { Meta, StoryObj } from "@storybook/react";
import RuntimePlayer from "@/components/dwo/RuntimePlayer";

const meta: Meta<typeof RuntimePlayer> = {
  title: "DWO/RuntimePlayer",
  component: RuntimePlayer,
  tags: ["autodocs"],
  argTypes: {
    mode: { control: "select", options: ["LIVE", "REPLAY", "SIMULATED"] },
    playing: { control: "boolean" },
  },
};
export default meta;

type Story = StoryObj<typeof RuntimePlayer>;

const base = {
  cursor: 0,
  len: 10,
  mode: "LIVE" as const,
  speed: 750,
  playing: false,
  label: "DEV-RUN-STORYBOOK-001 · G0_CONTEXT · Source Resolution",
  onFirst: () => {},
  onPrev: () => {},
  onToggle: () => {},
  onNext: () => {},
  onLast: () => {},
  onScrub: () => {},
  onMode: () => {},
  onSpeed: () => {},
};

export const live: Story = { args: { ...base, mode: "LIVE", playing: false } };
export const replay: Story = { args: { ...base, mode: "REPLAY", playing: false } };
export const paused: Story = { args: { ...base, mode: "LIVE", playing: false } };
export const start: Story = { args: { ...base, mode: "LIVE", playing: true, cursor: 0 } };
export const end: Story = { args: { ...base, mode: "REPLAY", playing: false, cursor: 9 } };