import { api, type RelationEntry } from "../api";
import { ModeTag, SectionHead } from "../components/Specimen";
import { Await } from "../components/States";
import { pct } from "../format";
import { useLoad } from "../hooks";

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
  const [data] = useLoad(() => api.relations(), []);
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
