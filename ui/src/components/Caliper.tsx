import { score as fmt } from "../format";

const at = (x: number) => `${Math.max(0, Math.min(1, x)) * 100}%`;

/**
 * Signature 5: the variance caliper. A 0-1 scale bar with the follow-up's agreement score (pin),
 * the threshold actually applied (dashed notch), and the source's own noise floor (hatched band
 * from its self-agreement up to 1). A pin left of the notch is a mutation.
 */
export function Caliper({
  score,
  threshold,
  selfAgreement,
  tone,
}: {
  score: number | null;
  threshold: number;
  selfAgreement: number | null;
  tone: string;
}) {
  const label =
    `agreement ${fmt(score)}, threshold ${fmt(threshold)}` +
    (selfAgreement !== null ? `, self-agreement ${fmt(selfAgreement)}` : "");
  return (
    <div className={`caliper ${tone}`} role="img" aria-label={label}>
      <div className="scale" />
      {[0, 0.25, 0.5, 0.75, 1].map((t) => (
        <div key={t} className="tick" style={{ left: at(t), height: t % 0.5 === 0 ? 9 : 5 }} />
      ))}
      {selfAgreement !== null && (
        <div className="noise" style={{ left: at(selfAgreement), width: at(1 - selfAgreement) }} />
      )}
      <div className="threshold" style={{ left: at(threshold) }} />
      {score !== null && <div className="score" style={{ left: at(score) }} />}
      <div className="ends">
        <span>0</span>
        <span>
          score {fmt(score)} · threshold {fmt(threshold)}
        </span>
        <span>1</span>
      </div>
    </div>
  );
}
