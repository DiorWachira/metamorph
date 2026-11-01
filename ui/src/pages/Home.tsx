import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import { Caliper } from "../components/Caliper";
import { Drawer, PinLegend } from "../components/Drawer";
import { DiffText, Plate } from "../components/Plate";
import { Figure, GateStamp, SectionHead, Stamp } from "../components/Specimen";
import { Await } from "../components/States";
import { pct, usd, when } from "../format";
import { useLoad } from "../hooks";

// A real case from examples/cv_skills: the extractor only reads skills after English cue
// phrases, so the same CV written in Sheng loses every skill.
const SOURCE_CV = "She is proficient in Python, SQL and Power BI.";
const FOLLOWUP_CV = "Yeye ni moto kwa Python, SQL na Power BI.";

function HeroPlate() {
  const [coloured, setColoured] = useState(false);
  return (
    <figure className={`hero-plate ${coloured ? "is-coloured" : ""}`}>
      <div className="mount">
        <img
          src="/plates/plate-vii.webp"
          width={1060}
          height={1410}
          alt="Merian's plate VII: a spiny caterpillar on a cherry branch and the blue Morpho butterfly it becomes."
        />
        <span className="mount-no label">Pl. VII</span>
      </div>
      <figcaption className="caption">
        <b className="label">Fig. 1</b> One species, two forms. Maria Sibylla Merian,{" "}
        <i>Metamorphosis insectorum Surinamensium</i>, pl. VII (1705). Koninklijke Bibliotheek, via
        Wikimedia Commons; public domain.{" "}
        <button className="link-button" onClick={() => setColoured((c) => !c)} aria-pressed={coloured}>
          {coloured ? "Show the engraving" : "Hand-colour the plate"}
        </button>
      </figcaption>
    </figure>
  );
}

function HowARelationReads() {
  return (
    <section>
      <SectionHead no="§1" title="How a relation is read" />
      <div className="reading">
        <figure className="reading-step">
          <img src="/plates/plate-vii-larva.webp" width={345} height={350} alt="The caterpillar, detail of plate VII." />
          <figcaption>
            <span className="label">I · The specimen</span>
            <p>
              A real input from your seed file. Nobody knows its correct answer, and nobody needs to.
            </p>
          </figcaption>
        </figure>
        <figure className="reading-step">
          <img src="/plates/plate-vii-imago.webp" width={660} height={630} alt="The blue Morpho butterfly, detail of plate VII." />
          <figcaption>
            <span className="label">II · The metamorphosis</span>
            <p>
              A transform changes its form the way real users do: Sheng, typos, reordered context, a
              politer tone.
            </p>
          </figcaption>
        </figure>
        <div className="reading-step reading-det">
          <span className="label">III · The determination</span>
          <p>
            Same species? A comparator checks the <em>relation</em> between the two answers. If they
            disagree more than the app disagrees with itself, it is a mutation.
          </p>
          <Stamp tone="carmine">Mutation</Stamp>
        </div>
      </div>

      <div className="worked">
        <div className="label worked-label">A worked specimen · cv_skills demo · code-switch-invariance</div>
        <Plate
          instar="code_switch · sheng"
          leftFig="Source input"
          rightFig="Follow-up input"
          left={<DiffText segments={[["equal", SOURCE_CV]]} />}
          right={<DiffText segments={[["insert", FOLLOWUP_CV]]} />}
        />
        <Plate
          instar="set_equal on $.skills"
          leftFig="Source output"
          rightFig="Follow-up output"
          numerals={["FIG. III", "FIG. IV"]}
          left={<code>{'{"skills": ["Power BI", "Python", "SQL"]}'}</code>}
          right={
            <code>
              {'{"skills": '}
              <ins className="diff-ins">[]</ins>
              {"}"}
            </code>
          }
        />
        <div className="worked-foot">
          <Caliper score={0} threshold={0.75} selfAgreement={0.8} tone="st-violation" />
          <p className="caption">
            The extractor only reads skills after English cue phrases. Its answers on the original
            CV agree with each other at 0.80 (the hatched noise floor), so the bar for a mutation is
            0.75. The Sheng CV scores 0: every skill is lost. No labelled answer was needed to see it.
          </p>
        </div>
      </div>
    </section>
  );
}

function LatestAccession() {
  const [overview] = useLoad(() => api.overview(), []);
  return (
    <section>
      <SectionHead no="§2" title="The latest accession">
        <Link to="/runs">All accessions →</Link>
      </SectionHead>
      <Await value={overview} what="the ledger">
        {(o) =>
          o.latest ? (
            <LatestRun id={o.latest.id} />
          ) : (
            <div className="caption">
              No runs stored yet. Run <code>metamorph run</code> in a project, then refresh.
            </div>
          )
        }
      </Await>
    </section>
  );
}

function LatestRun({ id }: { id: string }) {
  const [run] = useLoad(() => api.run(id), [id]);
  return (
    <Await value={run} what="the latest run">
      {(r) => (
        <div className="latest">
          <div className="latest-head">
            <div>
              <div className="label">
                Run {r.run.id} · {when(r.run.started_at)} · {usd(r.run.total_cost_usd)}
              </div>
              <p className="caption">
                {r.cases.length} specimens across {r.relations.length} relations, k = {r.run.samples}{" "}
                source samples each.
              </p>
            </div>
            <GateStamp gate={r.gate} />
          </div>
          <div className="figures">
            <Figure label="Mutations" value={r.baseline_effect.violations} tone="carmine" />
            <Figure label="Blocking" value={r.gate?.blocking_violations ?? 0} tone="carmine" />
            <Figure
              label="Excused by baseline"
              value={r.baseline_effect.excused}
              tone="ochre"
              note={r.run.samples > 1 ? "the app's own noise" : "single sample run"}
            />
            <Figure label="Unstable inputs" value={new Set(r.unstable_inputs.map((u) => u.seed_id)).size} />
          </div>
          <Drawer relations={r.relations} cases={r.cases} />
          <PinLegend />
          <Link to={`/runs/${r.run.id}`} className="btn primary">
            Examine the specimens
          </Link>
        </div>
      )}
    </Await>
  );
}

function TrustIsEarned() {
  const [overview] = useLoad(() => api.overview(), []);
  return (
    <section>
      <SectionHead no="§3" title="Trust is earned, per relation" />
      <div className="trust">
        <p className="lede">
          Every relation starts as a <span className="mode-tag">warning</span>. You determine each
          mutation as a true defect or a false alarm; once a relation has 20 determinations at 80%
          precision or better, it may <span className="mode-tag blocking">block</span> your pull
          requests.
        </p>
        <Await value={overview} what="determinations">
          {(o) => (
            <div className="det-slip trust-slip">
              <div className="det-line label">Determinations on file</div>
              <div className="det-line">
                {o.reviewed} reviewed · {o.true_bugs} true defects · {o.false_alarms} false alarms
              </div>
              <div className="det-line">
                Collection precision {pct(o.reviewed ? o.true_bugs / o.reviewed : null)}
              </div>
              <Link to="/relations">Open the collection →</Link>
            </div>
          )}
        </Await>
      </div>
    </section>
  );
}

export function Home() {
  return (
    <div className="home">
      <section className="hero">
        <div className="hero-copy">
          <div className="label">Metamorph · metamorphic testing for LLM applications</div>
          <h1>
            Same question,
            <br />
            new form.
            <br />
            <em>Same answer?</em>
          </h1>
          <p className="lede">
            LLM apps have no answer key. Metamorph doesn't need one: it rewrites each real input the
            way your users would (in Sheng, with typos, with the documents shuffled) and checks
            that the answer survives the metamorphosis. It runs in CI and gates your pull
            requests, and it learns which of its own tests to trust.
          </p>
          <div className="hero-actions">
            <Link to="/runs/latest" className="btn primary">
              Open the latest run
            </Link>
            <Link to="/lab" className="btn">
              Try a transform
            </Link>
          </div>
          <pre className="hero-cli" aria-label="Command line">
            <span className="caption">$</span> metamorph run --gate{"\n"}
            <span className="caption">Gate FAILED: 13 blocking violations · exit 1</span>
          </pre>
        </div>
        <HeroPlate />
      </section>
      <HowARelationReads />
      <LatestAccession />
      <TrustIsEarned />
    </div>
  );
}
