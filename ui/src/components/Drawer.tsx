import { Link } from "react-router-dom";

import type { CaseView, RelationSummary } from "../api";
import { caseClass, catalogueNo } from "../format";
import { ModeTag } from "./Specimen";

/** Signature 3: the specimen drawer. One unit tray per relation, one pin per case. */
export function Drawer({
  relations,
  cases,
  selected,
  onSelect,
}: {
  relations: RelationSummary[];
  cases: CaseView[];
  selected?: string | null;
  onSelect?: (id: string | null) => void;
}) {
  const byRelation = new Map<string, CaseView[]>();
  for (const c of cases) byRelation.set(c.relation_id, [...(byRelation.get(c.relation_id) ?? []), c]);

  return (
    <div className="drawer">
      {relations.map((r) => {
        const pins = byRelation.get(r.id) ?? [];
        const active = selected === r.id;
        return (
          <div key={r.id} className={`tray ${active ? "tray-active" : ""}`}>
            <div className="tray-head">
              <div>
                {onSelect ? (
                  <button
                    className="tray-name name"
                    aria-pressed={active}
                    onClick={() => onSelect(active ? null : r.id)}
                  >
                    {r.id}
                  </button>
                ) : (
                  <div className="name">{r.id}</div>
                )}
                <div className="label">
                  {r.transform} → {r.comparator}
                </div>
              </div>
              <ModeTag mode={r.mode} />
            </div>
            <div className="pins">
              {pins.length === 0 && <span className="caption">no specimens</span>}
              {pins.map((c) => (
                <Link
                  key={c.id}
                  to={`/cases/${c.id}`}
                  className={`pin ${caseClass(c)}`}
                  title={`${catalogueNo(c.id)} · ${c.seed_id} · ${c.excused_by_baseline ? "excused" : c.status}`}
                  aria-label={`${catalogueNo(c.id)} ${c.seed_id} ${c.status}`}
                />
              ))}
            </div>
            <div className="label">
              {r.violations} mutated · {r.passed} intact
              {r.excused ? ` · ${r.excused} excused` : ""}
              {r.inconclusive ? ` · ${r.inconclusive} inconclusive` : ""}
              {r.errors ? ` · ${r.errors} errors` : ""}
              {r.skipped ? ` · ${r.skipped} skipped` : ""}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function PinLegend() {
  return (
    <div className="legend">
      <span className="status-chip st-violation">mutation</span>
      <span className="status-chip st-intact">intact</span>
      <span className="status-chip st-excused">excused by baseline</span>
      <span className="status-chip st-inconclusive">inconclusive / error / skipped</span>
    </div>
  );
}
