import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api, type CaseDetail, type Triage } from "../api";
import { Caliper } from "../components/Caliper";
import { DiffText, Plate } from "../components/Plate";
import { SectionHead, SpecimenLabel, Stamp } from "../components/Specimen";
import { Await } from "../components/States";
import { useToast } from "../components/Toast";
import { TRIAGE_WORD, caseClass, catalogueNo, pct, score, show } from "../format";
import { useLoad } from "../hooks";

function DeterminationSlip({ detail, onSaved }: { detail: CaseDetail; onSaved: () => void }) {
  const c = detail.case;
  const toast = useToast();
  const [note, setNote] = useState(c.note ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const determine = useCallback(
    async (verdict: Triage) => {
      setSaving(true);
      setError(null);
      try {
        const { stats } = await api.triage(c.id, verdict, note.trim() || null);
        const learned = stats.learned_mode ? ` · now ${stats.learned_mode}` : "";
        toast(
          `${catalogueNo(c.id)}: ${TRIAGE_WORD[verdict]}`,
          `${c.relation_id} precision ${pct(stats.precision)} over ${stats.reviewed} reviews${learned}`,
        );
        onSaved();
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setSaving(false);
      }
    },
    [c.id, c.relation_id, note, onSaved, toast],
  );

  useEffect(() => {
    if (c.status !== "violation") return;
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLTextAreaElement || e.metaKey || e.ctrlKey || e.altKey) return;
      const key = e.key.toLowerCase();
      if (key === "t") void determine("true_bug");
      if (key === "f") void determine("false_alarm");
      if (key === "u") void determine("unreviewed");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [c.status, determine]);

  if (c.status !== "violation") {
    return (
      <div className="det-slip">
        <div className="det-line label">Determination</div>
        <p className="caption">
          Only mutations are determined. This specimen is {c.excused_by_baseline ? "excused by the baseline" : c.status}.
        </p>
      </div>
    );
  }

  return (
    <div className="det-slip determination">
      <div className="det-line label">Det. slip · {catalogueNo(c.id)}</div>
      <div className="det-line det-current">
        {c.triage === "unreviewed" ? (
          <span className="caption">Not yet determined.</span>
        ) : (
          <Stamp key={c.triage} tone={c.triage === "true_bug" ? "carmine" : "ink"}>
            {TRIAGE_WORD[c.triage]}
          </Stamp>
        )}
      </div>
      <label className="det-line det-note">
        <span className="label">Note</span>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={3}
          placeholder="Why? (e.g. the judge missed a synonym)"
        />
      </label>
      <div className="det-actions">
        <button className="btn" disabled={saving} onClick={() => determine("true_bug")}>
          True defect <kbd>T</kbd>
        </button>
        <button className="btn" disabled={saving} onClick={() => determine("false_alarm")}>
          False alarm <kbd>F</kbd>
        </button>
        {c.triage !== "unreviewed" && (
          <button className="btn link-button" disabled={saving} onClick={() => determine("unreviewed")}>
            Clear <kbd>U</kbd>
          </button>
        )}
      </div>
      {error && <p className="caption ink-carmine">{error}</p>}
    </div>
  );
}

function CaseBody({ detail, reload }: { detail: CaseDetail; reload: () => void }) {
  const c = detail.case;
  const navigate = useNavigate();
  const { previous, next } = detail.neighbours;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLTextAreaElement || e.metaKey || e.ctrlKey || e.altKey) return;
      if ((e.key === "j" || e.key === "ArrowRight") && next) navigate(`/cases/${next}`);
      if ((e.key === "k" || e.key === "ArrowLeft") && previous) navigate(`/cases/${previous}`);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate, next, previous]);

  return (
    <div>
      <nav className="crumbs label" aria-label="Breadcrumb">
        <Link to={`/runs/${c.run_id}`}>Run {c.run_id}</Link> / {catalogueNo(c.id)}
      </nav>
      <div className="case-layout">
        <div className="case-main">
          <h1 className="case-title">
            <em>{c.relation_id}</em>
            <span className="caption"> on seed {c.seed_id}</span>
          </h1>
          <p className="lede">{c.detail}</p>

          <SectionHead no="§1" title="The answers" />
          <Plate
            instar={c.relation_id}
            leftFig="Source output"
            rightFig="Follow-up output"
            left={<DiffText segments={detail.output_diff.left} />}
            right={<DiffText segments={detail.output_diff.right} />}
          />

          <SectionHead no="§2" title="The metamorphosis" />
          <p className="caption">{c.followup_note}</p>
          {detail.changed_field ? (
            <Plate
              instar={detail.changed_field}
              leftFig={`Source · ${detail.changed_field}`}
              rightFig={`Follow-up · ${detail.changed_field}`}
              numerals={["I", "II"]}
              left={<DiffText segments={detail.input_diff.left} />}
              right={<DiffText segments={detail.input_diff.right} />}
            />
          ) : (
            <p className="caption">The input is unchanged at the top level.</p>
          )}
          <details className="raw">
            <summary className="label">Full inputs</summary>
            <div className="raw-grid">
              <pre>{show(c.source_input)}</pre>
              <pre>{show(c.followup_input)}</pre>
            </div>
          </details>

          {c.source_outputs.length > 1 && (
            <>
              <SectionHead no="§3" title={`The ${c.source_outputs.length} source samples`} />
              <p className="caption">
                The same input, sent {c.source_outputs.length} times. Their lowest agreement with each
                other ({score(c.self_variance)}) is this specimen's noise floor.
              </p>
              <ol className="samples">
                {c.source_outputs.map((o) => (
                  <li key={o.sample_idx}>
                    <span className="label">sample {o.sample_idx}</span>
                    <span className="sample-text">{o.error ? `error: ${o.error}` : o.text}</span>
                  </li>
                ))}
              </ol>
            </>
          )}
        </div>

        <aside className="case-side">
          <SpecimenLabel c={c} />
          <div className="side-block">
            <div className="label">Measurement</div>
            <Caliper score={c.score} threshold={c.threshold} selfAgreement={c.self_variance} tone={caseClass(c)} />
            <dl className="measure-list">
              <dt>agreement</dt>
              <dd>{score(c.score)}</dd>
              <dt>threshold applied</dt>
              <dd>{score(c.threshold)}</dd>
              <dt>comparator threshold</dt>
              <dd>{score(c.nominal_threshold)}</dd>
              <dt>self-agreement</dt>
              <dd>{c.self_variance === null ? "not measured (k = 1)" : score(c.self_variance)}</dd>
            </dl>
          </div>
          <DeterminationSlip key={c.id} detail={detail} onSaved={reload} />
          <div className="case-nav">
            <button className="btn" disabled={!previous} onClick={() => previous && navigate(`/cases/${previous}`)}>
              ← Previous <kbd>K</kbd>
            </button>
            <button className="btn" disabled={!next} onClick={() => next && navigate(`/cases/${next}`)}>
              Next <kbd>J</kbd> →
            </button>
          </div>
        </aside>
      </div>
    </div>
  );
}

export function CasePage() {
  const { caseId } = useParams();
  const id = Number(caseId);
  const [detail, reload] = useLoad(() => api.case(id), [id]);
  return (
    <Await value={detail} what="the specimen">
      {(d) => <CaseBody detail={d} reload={reload} />}
    </Await>
  );
}
