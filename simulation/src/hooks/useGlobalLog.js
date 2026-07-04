import { useEffect, useState } from 'react';
import { useSISP } from '../context/SISPContext.jsx';

const POLL_MS = 300;

// Polls the global event ring buffer kept on ProtocolService.globalLog.
// Returns the array sorted newest-first.
export function useGlobalLog() {
  const { refs, ready } = useSISP();
  const [log, setLog] = useState([]);

  useEffect(() => {
    if (!ready) return;
    const protocol = refs.current.protocol;
    const update = () => setLog(protocol.globalLog.slice());
    update();
    const id = setInterval(update, POLL_MS);
    return () => clearInterval(id);
  }, [ready, refs]);

  return log;
}
