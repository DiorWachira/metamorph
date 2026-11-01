import { useState, type FormEvent } from "react";

import { api, type LabResponse } from "../api";
import { DiffText, Plate } from "../components/Plate";
import { SectionHead } from "../components/Specimen";

const TRANSFORMS = [
  { id: "typos", label: "Typos", help: "keyboard slips on words of 4+ letters; numbers untouched" },
  { id: "number_format", label: "Number format", help: "1000 ↔ 1,000; years left alone" },
  { id: "swap_entities", label: "Swap names", help: "Kenyan names swapped consistently, mapped back later" },
  { id: "surface_noise", label: "Surface noise", help: "casing, spacing and punctuation" },
  { id: "inject_distractor", label: "Distractor", help: "an irrelevant paragraph joins the context" },
  { id: "shuffle_documents", label: "Shuffle documents", help: "the retrieved context, reordered" },
] as const;

const EXAMPLE_TEXT = "Wanjiru wants to know: did Safaricom launch M-Pesa in March 2007, and does it cost 1000 shillings?";
const EXAMPLE_DOCS = [
  "M-Pesa is a mobile money service launched by Safaricom in Kenya in March 2007.",
  "Nairobi National Park was established in 1946.",
  "Kenya Vision 2030 was launched in 2008.",
];

export function Lab() {
  const [transform, setTransform] = useState<string>("typos");
  const [text, setText] = useState(EXAMPLE_TEXT);
  const [docs, setDocs] = useState(EXAMPLE_DOCS.join("\n"));
  const [rate, setRate] = useState(0.3);
  const [seed, setSeed] = useState(0);
  const [result, setResult] = useState<LabResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(e?: FormEvent, nextSeed = seed) {
    e?.preventDefault();
    setError(null);
    try {
      setResult(
        await api.lab({
          transform,
          params: transform === "typos" ? { rate } : {},
          text,
          documents: docs.split("\n").map((d) => d.trim()).filter(Boolean),
          seed: nextSeed,
        }),
      );
    } catch (err) {
      setResult(null);
      setError((err as Error).message);
    }
  }

  const usesDocs = transform === "shuffle_documents" || transform === "inject_distractor";
  const help = TRANSFORMS.find((t) => t.id === transform)?.help;

  return (
    <div>
      <header className="page-head">
        <div className="label">The lab</div>
        <h1>Try a transform</h1>
        <p className="lede measure">
          The deterministic transforms a run applies to your seeds, applied to any text you like. Same
          seed, same follow-up: that is what makes re-runs free.
        </p>
      </header>
      <form className="lab" onSubmit={run}>
        <fieldset className="lab-transforms">
          <legend className="label">Transform</legend>
          {TRANSFORMS.map((t) => (
            <button
              type="button"
              key={t.id}
              className="btn"
              aria-pressed={transform === t.id}
              onClick={() => {
                setTransform(t.id);
                setResult(null);
              }}
            >
              {t.label}
            </button>
          ))}
          <p className="caption">{help}</p>
        </fieldset>
        <label className="lab-field">
          <span className="label">Specimen · question</span>
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} maxLength={5000} />
        </label>
        {usesDocs && (
          <label className="lab-field">
            <span className="label">Retrieved documents · one per line</span>
            <textarea value={docs} onChange={(e) => setDocs(e.target.value)} rows={4} />
          </label>
        )}
        {transform === "typos" && (
          <label className="lab-field lab-inline">
            <span className="label">Rate {rate.toFixed(2)}</span>
            <input type="range" min={0.05} max={1} step={0.05} value={rate} onChange={(e) => setRate(Number(e.target.value))} />
          </label>
        )}
        <div className="lab-actions">
          <button className="btn primary" type="submit">
            Metamorphose
          </button>
          <button
            className="btn"
            type="button"
            onClick={() => {
              setSeed(seed + 1);
              void run(undefined, seed + 1);
            }}
          >
            Another seed
          </button>
          <span className="label">seed {seed}</span>
        </div>
      </form>

      {error && <p className="caption ink-carmine">{error}</p>}
      {result && (
        <section>
          <SectionHead no="§1" title="The follow-up" />
          <p className="caption">{result.note}</p>
          {!usesDocs && (
            <Plate
              instar={transform}
              leftFig="Source"
              rightFig="Follow-up"
              left={<DiffText segments={result.diff.left} />}
              right={<DiffText segments={result.diff.right} />}
            />
          )}
          {usesDocs && (
            <ol className="lab-docs">
              {result.documents.map((d, i) => (
                <li key={i} className={docs.includes(d) ? "" : "lab-doc-new"}>
                  {d}
                </li>
              ))}
            </ol>
          )}
        </section>
      )}
    </div>
  );
}
