import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import type { Loadable } from "../hooks";

export function Loading({ what = "specimens" }: { what?: string }) {
  return (
    <div className="state" role="status">
      <span className="loading-pins" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
      <span className="label">Pinning {what}…</span>
    </div>
  );
}

export function ErrorState({ error }: { error: Error }) {
  return (
    <div className="state state-error" role="alert">
      <span className="stamp slate">Specimen damaged</span>
      <p className="caption">{error.message}</p>
      <p className="caption">
        Is the API running? Start it with <code>metamorph serve</code>.
      </p>
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="state state-empty">
      <h3>{title}</h3>
      <div className="caption">{children}</div>
      <Link to="/lab" className="btn">
        Try a transform in the lab
      </Link>
    </div>
  );
}

/** Render a Loadable: loading and error states are uniform across pages. */
export function Await<T>({
  value,
  what,
  children,
}: {
  value: Loadable<T>;
  what?: string;
  children: (data: T) => ReactNode;
}) {
  if (value.state === "loading") return <Loading what={what} />;
  if (value.state === "error") return <ErrorState error={value.error} />;
  return <>{children(value.data)}</>;
}
