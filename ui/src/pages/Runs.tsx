import { Link } from "react-router-dom";

import { api } from "../api";
import { SectionHead, Stamp } from "../components/Specimen";
import { Await, Empty } from "../components/States";
import { shortSha, usd, when } from "../format";
import { useLoad } from "../hooks";

/** The accession ledger: every run, newest first. */
export function Runs() {
  const [runs] = useLoad(() => api.runs(), []);
  return (
    <div>
      <header className="page-head">
        <div className="label">The ledger</div>
        <h1>Accessions</h1>
        <p className="caption">Every run is an accession: a dated survey of your seed specimens.</p>
      </header>
      <SectionHead no="§1" title="Register" />
      <Await value={runs} what="the ledger">
        {(list) =>
          list.length === 0 ? (
            <Empty title="The ledger is empty">
              Run <code>metamorph run</code> in this project to record the first accession.
            </Empty>
          ) : (
            <div className="table-scroll">
              <table className="ledger">
                <thead>
                  <tr>
                    <th>Accession</th>
                    <th>Commit</th>
                    <th className="num">Specimens</th>
                    <th className="num">Mutations</th>
                    <th className="num">Blocking</th>
                    <th className="num">Cost</th>
                    <th>Gate</th>
                  </tr>
                </thead>
                <tbody>
                  {list.map((r) => (
                    <tr key={r.id}>
                      <td>
                        <Link to={`/runs/${r.id}`} className="mono">
                          {r.id}
                        </Link>
                        <div className="caption">{when(r.started_at)}</div>
                      </td>
                      <td className="mono">{shortSha(r.git_sha)}</td>
                      <td className="num">{r.cases}</td>
                      <td className={`num ${r.violations ? "ink-carmine" : ""}`}>{r.violations}</td>
                      <td className="num">{r.blocking_violations}</td>
                      <td className="num">{usd(r.total_cost_usd)}</td>
                      <td>
                        {r.status === "running" ? (
                          <span className="label">running</span>
                        ) : r.gate_passed === null ? (
                          <span className="label">{r.status}</span>
                        ) : (
                          <Stamp tone={r.gate_passed ? "verdigris" : "carmine"}>
                            {r.gate_passed ? "Passed" : "Failed"}
                          </Stamp>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }
      </Await>
    </div>
  );
}
