import { useEffect, useState } from 'react';
import { useSISP } from '../context/SISPContext.jsx';
import { GROUND_STATIONS } from '../constants/index.js';
import { losToStation } from '../utils/los.js';

const POLL_MS = 1000;

// Returns [{ id, name, lat_deg, lon_deg, contact: bool }] — `contact` is true
// when at least one satellite has line-of-sight to that ground station.
export function useGroundContacts() {
  const { refs, ready } = useSISP();
  const [stations, setStations] = useState(
    GROUND_STATIONS.map((s) => ({ ...s, contact: false }))
  );

  useEffect(() => {
    if (!ready) return;
    const engine = refs.current.engine;
    const update = () => {
      const out = GROUND_STATIONS.map((s) => {
        let contact = false;
        for (const sat of engine.sats) {
          if (losToStation(sat.currentPos, s)) {
            contact = true;
            break;
          }
        }
        return { ...s, contact };
      });
      setStations(out);
    };
    update();
    const id = setInterval(update, POLL_MS);
    return () => clearInterval(id);
  }, [ready, refs]);

  return stations;
}
