import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api, type CaseView, type RunReport } from "../api";
import { Caliper } from "../components/Caliper";
import { Drawer, PinLegend } from "../components/Drawer";
import { Figure, GateStamp, ModeTag, SectionHead, StatusChip } from "../components/Specimen";
import { Await } from "../components/States";
import { TRIAGE_WORD, caseClass, catalogueNo, score, shortSha, usd, when } from "../format";
import { useLoad } from "../hooks";

type Filter = "violations" | "excused" | "all";

function matches(c: CaseView, filter: Filter, relation: string | null): boolean {
  if (relation && c.relation_id !== relation) return false;
  if (filter === "violations") return c.status === "violation";
  if (filter === "excused") return c.excused_by_baseline;
  return true;
}

function Specimens({ report }: { report: RunReport }) {
  const [filter, setFilter] = useState<Filter>("violations");
  const [relation, setRelation] = useState<string | null>(null);
  const shown = useMemo(
    () => report.cases.filter((c) => matches(c, filter, relation)),
    [report.cases, filter, relation],
  );
  const counts: Record<Filter, number> = {
    violations: report.cases.filter((c) => c.status === "violation").length,
    excused: report.cases.filter((c) => c.excused_by_baseline).length,
    all: report.cases.length,
  };

  return (
    <>
      <SectionHead no="§2" title="The drawer">
        <span className="caption">Select a tray to filter the specimens below.</span>
      </SectionHead>
      <Drawer relations={report.relations} cases={report.cases} selected={relation} onSelect={setRelation} />
      <PinLegend />

      <SectionHead no="§3" title="Specimens" />
      <div className="filters" role="group" aria-label="Filter specimens">
        {(["violations", "excused", "all"] as Filter[]).map((f) => (
          <button key={f} className="btn" aria-pressed={filter === f} onClick={() => setFilter(f)}>
            {f === "violations" ? "Mutations" : f === "excused" ? "Excused by baseline" : "All"}
            <span className="numeral"> {counts[f]}</span>
          </button>
        ))}
        {relation && (
          <button className="btn" onClick={() => setRelation(null)}>
            {relation} ✕
          </button>
        )}
      </div>
      {shown.length === 0 ? (
        <p className="caption">No specimens match this filter.</p>
      ) : (
        <ol className="specimen-list">
          {shown.map((c) => (
            <li key={c.id}>
              <Link to={`/cases/${c.id}`} className="specimen-row">
                <span className="mono specimen-row-no">{catalogueNo(c.id)}</span>
                <span className="specimen-row-main">
                  <span className="specimen-row-taxon">{c.relation_id}</span>
                  <span className="caption">
                    seed {c.seed_id} · {c.detail}
                  </span>
                </span>
                <span className="specimen-row-caliper">
                  <Caliper score={c.score} threshold={c.threshold} selfAgreement={c.self_variance} tone={caseClass(c)} />
                </span>
                <span className="specimen-row-meta">
                  <StatusChip c={c} />
                  <ModeTag mode={c.mode} />
                  {c.status === "violation" && (
                    <span className={`label triage-word triage-${c.triage}`}>{TRIAGE_WORD[c.triage]}</span>
                  )}
                </span>
              </Link>
            </li>
          ))}
        </ol>
      )}
    </>
  );
}

function Unstable({ report }: { report: RunReport }) {
  return (
    <>
      <SectionHead no="§4" title="Unstable specimens" />
      {report.run.samples === 1 ? (
        <p className="caption">
          Not measured: this run took one sample per input. Set <code>run.samples: 3</code> to see
          which inputs your app answers inconsistently on its own.
        </p>
      ) : report.unstable_inputs.length === 0 ? (
        <p className="caption">Every input agreed with itself across all {report.run.samples} samples.</p>
      ) : (
        <>
          <p className="caption measure">
            These inputs disagree with themselves before any transform. Violations on them say more
            about sampling noise than about the relation, so the baseline loosens the bar for them.
          </p>
          <div className="table-scroll">
            <table className="ledger">
              <thead>
                <tr>
                  <th>Seed</th>
                  <th>Comparator</th>
                  <th className="num">Self-agreement</th>
                  <th className="num">Threshold</th>
                  <th>Relations affected</th>
                </tr>
              </thead>
              <tbody>
                {report.unstable_inputs.map((u) => (
                  <tr key={`${u.seed_id}-${u.comparator}`}>
                    <td className="mono">{u.seed_id}</td>
                    <td className="mono">{u.comparator}</td>
                    <td className="num">{score(u.self_agreement)}</td>
                    <td className="num">{score(u.threshold)}</td>
                    <td className="caption">{u.relations.join(", ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </>
  );
}

export function RunPage() {
  const { runId = "latest" } = useParams();
  const [run] = useLoad(() => api.run(runId), [runId]);
  return (
    <Await value={run} what="the accession">
      {(r) => (
        <div>
          <header className="page-head masthead-run">
            <div>
              <div className="label">Run accession</div>
              <h1 className="run-id">{r.run.id}</h1>
              <div className="meta label">
                <span>{when(r.run.started_at)}</span>
                <span>commit {shortSha(r.run.git_sha)}</span>
                <span>k = {r.run.samples}</span>
                <span>cost {usd(r.run.total_cost_usd)}</span>
                {r.run.llm && <span>helper {r.run.llm.model}</span>}
                {r.run.status === "budget_exhausted" && <span className="ink-carmine">budget exhausted</span>}
              </div>
            </div>
            <GateStamp gate={r.gate} />
          </header>

          <SectionHead no="§1" title="Findings" />
          <div className="figures">
            <Figure label="Specimens" value={r.cases.length} />
            <Figure label="Mutations" value={r.baseline_effect.violations} tone="carmine" />
            <Figure label="Blocking" value={r.gate?.blocking_violations ?? 0} tone="carmine" />
            <Figure
              label="Excused by baseline"
              value={r.baseline_effect.excused}
              tone="ochre"
              note={
                r.run.samples > 1
                  ? `${r.baseline_effect.naive_violations} without the baseline`
                  : "needs k > 1"
              }
            />
          </div>
          {r.gate && r.gate.reasons.length > 0 && <p className="caption">Gate: {r.gate.reasons.join("; ")}.</p>}
          <Specimens report={r} />
          <Unstable report={r} />
          {r.skipped.length > 0 && (
            <>
              <SectionHead no="§5" title="Not examined" />
              <details>
                <summary className="label">{r.skipped.length} relation × seed pairs were skipped</summary>
                <ul className="skips caption">
                  {r.skipped.map((s, i) => (
                    <li key={i}>
                      <span className="mono">{s.seed_id}</span> · {s.relation_id}: {s.reason}
                    </li>
                  ))}
                </ul>
              </details>
            </>
          )}
        </div>
      )}
    </Await>
  );
}
