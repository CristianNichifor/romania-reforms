import { readFileSync } from 'node:fs';
import { decode } from '../../../../administrativ/web/src/model/load';
import { assign, readScenario, type Coupled, type CourtDistanceMeta } from '../../src/arondare';
import { proposedCourts } from '../../src/propuse';
import { publicData } from './helpers';

const binary = (name: string): ArrayBuffer => {
  const bytes = readFileSync(new URL(`../../public/data/${name}`, import.meta.url));
  return Uint8Array.from(bytes).buffer;
};

export function expectedProposal(hash: string) {
  const data = decode({
    manifest: publicData('admin-manifest.json'), attributes: publicData('admin-attributes.json'),
    attributesBin: binary('admin-attributes.bin'), adjacencyBin: binary('admin-adjacency.bin'),
    candidacyBin: binary('admin-candidacy.bin'),
  });
  const meta: CourtDistanceMeta = publicData('court-distance.json');
  const scenario = readScenario(hash);
  const coupled: Coupled = { data, meta, distance: new Uint16Array(binary(meta.file)),
    rowOfCounty: new Map(meta.courts.map((court, row) => [court.county, row])),
    defaults: readScenario('').params };
  const file = publicData('portal-instante.json');
  return proposedCourts(assign(coupled, scenario.params, scenario.pins), coupled,
    publicData('arondare-instante.json'), file, file.praguriZile);
}
