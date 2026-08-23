import type { RuntimeNode } from "@/lib/loginEpicRuntimeGraph";

/**
 * FamilyBandNode — a faint visual band grouping nodes of the same family inside
 * a gate. Purely decorative (no interaction). data-testid carries family.
 */
export default function FamilyBandNode({
  data,
}: {
  data: { family: string; boundary: string };
}) {
  const { family, boundary } = data;
  return (
    <div
      className={`leg-family-band leg-boundary-${boundary}`}
      data-testid="runtime-family-band"
      data-family={family}
    >
      <span className="leg-family-band-label">{family}</span>
    </div>
  );
}
