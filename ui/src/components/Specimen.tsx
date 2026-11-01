import type { ReactNode } from "react";

import type { CaseView, GateResult, Mode } from "../api";
import { STATUS_WORD, caseClass, catalogueNo } from "../format";

export function ModeTag({ mode }: { mode: Mode }) {
  return <span className={`mode-tag ${mode}`}>{mode}</span>;
}

export function StatusChip({ c }: { c: Pick<CaseView, "status" | "excused_by_baseline"> }) {
  const word = c.excused_by_baseline ? "excused" : STATUS_WORD[c.status];
  return <span className={`status-chip ${caseClass(c)}`}>{word}</span>;
}

/** Signature 1: the pin label every specimen (case) carries. */
export function SpecimenLabel({ c, children }: { c: CaseView; children?: ReactNode }) {
  return (
    <div className="specimen-label">
      <div className="cat">{catalogueNo(c.id)}</div>
      <div className="taxon">{c.relation_id}</div>
      <div>
        seed {c.seed_id}
        {c.variant ? ` · v${c.variant}` : ""}
      </div>
      <div className="specimen-label-foot">
        <ModeTag mode={c.mode} />
        <StatusChip c={c} />
      </div>
      {children}
    </div>
  );
}

/** Signature 4: the rubber stamp. */
export function Stamp({ tone, children }: { tone: "carmine" | "ink" | "verdigris" | "slate"; children: ReactNode }) {
  return <span className={`stamp ${tone}`}>{children}</span>;
}

export function GateStamp({ gate }: { gate: GateResult | null }) {
  if (!gate) return <Stamp tone="slate">No gate</Stamp>;
  if (gate.too_many_errors) return <Stamp tone="slate">Target failing</Stamp>;
  return gate.passed ? <Stamp tone="verdigris">Gate passed</Stamp> : <Stamp tone="carmine">Gate failed</Stamp>;
}

export function SectionHead({ no, title, children }: { no: string; title: string; children?: ReactNode }) {
  return (
    <div className="section-head">
      <span className="section-no">{no}</span>
      <h2>{title}</h2>
      {children && <div className="section-aside">{children}</div>}
    </div>
  );
}

export function Figure({
  label,
  value,
  tone,
  note,
}: {
  label: string;
  value: ReactNode;
  tone?: "carmine" | "ochre";
  note?: ReactNode;
}) {
  return (
    <div className={`figure ${tone ?? ""}`}>
      <div className="label">{label}</div>
      <div className="figure-n numeral">{value}</div>
      {note && <div className="caption">{note}</div>}
    </div>
  );
}
