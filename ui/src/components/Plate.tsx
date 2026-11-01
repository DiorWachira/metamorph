import type { ReactNode } from "react";

import type { Segment } from "../api";

/** Render one side of a word diff: deletions struck on the left, insertions underlined right. */
export function DiffText({ segments }: { segments: Segment[] }) {
  return (
    <>
      {segments.map(([op, text], i) =>
        op === "delete" ? (
          <del key={i} className="diff-del">
            {text}
          </del>
        ) : op === "insert" ? (
          <ins key={i} className="diff-ins">
            {text}
          </ins>
        ) : (
          <span key={i}>{text}</span>
        ),
      )}
    </>
  );
}

/** Signature 2: the metamorphosis plate, two forms of one specimen side by side. */
export function Plate({
  left,
  right,
  leftFig = "Source",
  rightFig = "Follow-up",
  instar,
  numerals = ["FIG. I", "FIG. II"],
}: {
  left: ReactNode;
  right: ReactNode;
  leftFig?: string;
  rightFig?: string;
  instar: string;
  numerals?: [string, string];
}) {
  return (
    <div className="plate">
      <div className="plate-form">
        <div className="fig">
          <b>{numerals[0]}</b>
          {leftFig}
        </div>
        <div className="body">{left}</div>
      </div>
      <div className="plate-instar" aria-label={`transform: ${instar}`}>
        ↓ {instar}
      </div>
      <div className="plate-form">
        <div className="fig">
          <b>{numerals[1]}</b>
          {rightFig}
        </div>
        <div className="body">{right}</div>
      </div>
    </div>
  );
}
