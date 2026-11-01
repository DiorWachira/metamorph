import { Link } from "react-router-dom";

import { ColourPlate } from "../components/Alive";
import { Stamp } from "../components/Specimen";

export function NotFound() {
  return (
    <div className="not-found">
      <figure className="mount not-found-plate">
        <ColourPlate src="/plates/plate-viii.webp" width={900} height={1265} alt="Merian's plate VIII: frangipani with moths." />
      </figure>
      <div className="not-found-copy">
        <div className="label">Error 404 · catalogue lookup</div>
        <h1>
          No specimen
          <br />
          <em>under this number.</em>
        </h1>
        <p className="lede">
          It may belong to a run that was deleted, or it was never collected. The cabinet keeps every
          accession it has recorded.
        </p>
        <Stamp tone="slate">Not in collection</Stamp>
        <div className="hero-actions">
          <Link to="/runs" className="btn primary">
            Browse the accessions
          </Link>
          <Link to="/" className="btn">
            Back to the cabinet
          </Link>
        </div>
      </div>
    </div>
  );
}
