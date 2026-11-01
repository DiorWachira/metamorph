import { useState } from "react";

import { api, type Proposal, type RelationEntry } from "../api";
import { ModeTag, SectionHead } from "../components/Specimen";
import { Await } from "../components/States";
import { useToast } from "../components/Toast";
import { pct } from "../format";
import { useLoad } from "../hooks";

const params = (p: Record<string, unknown>) =>
  Object.keys(p).length ? JSON.stringify(p) : "";

/**
 * Proposals from `metamorph mine`, each shown as a determination slip quoting the requirement it
 * was derived from. Approving writes it into relations/custom.yaml.
 */
function Proposals({ onDecided }: { onDecided: () => void }) {
  const [list, reload] = useLoad(() => api.proposals(), []);
  const [busy, setBusy] = useState<string | null>(null);
  const toast = useToast();

  async function decide(p: Proposal, decision: "approve" | "reject") {
    setBusy(p.spec.id);
    try {
      await api.decide(p.spec.id, decision);
      toast(
        `${p.spec.id}: ${decision === "approve" ? "accessioned" : "rejected"}`,
        decision === "approve" ? "written to relations/custom.yaml; enabled on the next run" : undefined,
      );
      reload();
      onDecided();
    } finally {
      setBusy(null);
    }
  }

  return (
    <Await value={list} what="proposals">
      {(proposals) =>
        proposals.length === 0 ? null : (
          <section>
            <SectionHead no="§0" title="Proposed by the miner">
              <span className="caption">Derived from your requirements; nothing runs until you approve it.</span>
            </SectionHead>
            <div className="proposals">
              {proposals.map((p) => (
                <article key={p.spec.id} className="det-slip proposal">
                  <div className="det-line label">
                    Proposal · from {p.source || "requirements"} · {p.model}
                  </div>
                  <h3 className="proposal-id">{p.spec.id}</h3>
                  {p.spec.requirement && <blockquote className="requirement">“{p.spec.requirement}”</blockquote>}
                  <p className="caption">{p.spec.description}</p>
                  <div className="det-line mono proposal-recipe">
                    {p.spec.transform.name}
                    {params(p.spec.transform.params) && <span className="muted"> {params(p.spec.transform.params)}</span>}
                    {" → "}
                    {p.spec.comparator.name}
                    {p.spec.comparator.threshold !== null && ` ≥ ${p.spec.comparator.threshold}`}
                    {p.spec.expected === "flips" && <b> · must flip</b>}
                  </div>
                  {p.rationale && (
                    <p className="caption">
                      <span className="label">Bug it targets · </span>
                      {p.rationale}
                    </p>
                  )}
                  <div className="det-actions">
                    <button className="btn primary" disabled={busy === p.spec.id} onClick={() => decide(p, "approve")}>
                      Approve
                    </button>
                    <button className="btn" disabled={busy === p.spec.id} onClick={() => decide(p, "reject")}>
                      Reject
                    </button>
                  </div>
                </article>
              ))}
            </div>
          </section>
        )
      }
    </Await>
  );
}

const SOURCE_WORD: Record<string, string> = {
  config: "pinned in metamorph.yaml",
  learned: "earned through triage",
  default: "default until 20 determinations",
};

/**
 * The precision meter. Two series (true defects in carmine, false alarms in hatched ochre),
 * validated for colour-vision deficiency in both themes, labelled directly so identity never
 * rests on colour alone. Tick marks show the promotion rule: 20 reviews, 80% precision.
 */
function PrecisionMeter({
  entry,
  minReviewed,
  minPrecision,
}: {
  entry: RelationEntry;
  minReviewed: number;
  minPrecision: number;
}) {
  const s = entry.stats;
  const reviewed = s?.reviewed ?? 0;
  const scale = Math.max(minReviewed, reviewed);
  const width = (n: number) => `${(n / scale) * 100}%`;
  return (
    <div className="meter">
      <div
        className="meter-track"
        role="img"
        aria-label={`${s?.true_bugs ?? 0} true defects and ${s?.false_alarms ?? 0} false alarms out of ${minReviewed} needed`}
      >
        {s && s.true_bugs > 0 && <div className="meter-seg seg-true" style={{ width: width(s.true_bugs) }} />}
        {s && s.false_alarms > 0 && <div className="meter-seg seg-false" style={{ width: width(s.false_alarms) }} />}
        <div className="meter-goal" style={{ left: width(minReviewed) }} title={`${minReviewed} reviews`} />
      </div>
      <div className="meter-labels label">
        <span>
          <i className="key key-true" /> {s?.true_bugs ?? 0} true
        </span>
        <span>
          <i className="key key-false" /> {s?.false_alarms ?? 0} false
        </span>
        <span>
          {reviewed}/{minReviewed} reviewed
        </span>
        <span className={s?.precision !== null && s?.precision !== undefined && s.precision >= minPrecision ? "" : "muted"}>
          precision {pct(s?.precision ?? null)}
        </span>
      </div>
    </div>
  );
}

export function Relations() {
  const [data, reload] = useLoad(() => api.relations(), []);
  return (
    <div>
      <header className="page-head">
        <div className="label">The collection</div>
        <h1>Relations</h1>
        <p className="lede measure">
          Each relation is a hypothesis about your app: <em>this change of form must not change the
          answer</em>. Triage measures how often it is right. A relation blocks CI only once it has
          earned it.
        </p>
      </header>
      <Proposals onDecided={reload} />
      <Await value={data} what="the collection">
        {(d) => (
          <>
            <SectionHead no="§1" title="Catalogue">
              <span className="caption">
                Promotion: {d.min_reviewed} determinations at ≥ {pct(d.min_precision)} precision.
              </span>
            </SectionHead>
            <ol className="catalogue">
              {d.relations.map((r, i) => (
                <li key={r.id} className={`entry ${r.enabled ? "" : "entry-off"}`}>
                  <div className="entry-no mono">{String(i + 1).padStart(2, "0")}</div>
                  <div className="entry-body">
                    <div className="entry-head">
                      <h3>{r.id}</h3>
                      <ModeTag mode={r.mode} />
                      {!r.enabled && <span className="label">not enabled</span>}
                      {r.llm && <span className="label">LLM</span>}
                    </div>
                    <p className="caption">{r.description}</p>
                    {r.requirement && <blockquote className="requirement">“{r.requirement}”</blockquote>}
                    <div className="label">
                      {r.transform} → {r.comparator}
                      {r.tags.length > 0 && ` · tags ${r.tags.join(", ")}`} · {SOURCE_WORD[r.mode_source]}
                    </div>
                  </div>
                  <PrecisionMeter entry={r} minReviewed={d.min_reviewed} minPrecision={d.min_precision} />
                </li>
              ))}
            </ol>
          </>
        )}
      </Await>
    </div>
  );
}
