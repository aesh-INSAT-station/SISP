import { useSISP } from '../context/SISPContext.jsx';

export function usePlayback() {
  const { refs, ready } = useSISP();

  if (!ready) {
    return {
      togglePlay: () => {},
      setMultiplier: () => {},
      stepBack: () => {},
      stepForward: () => {},
    };
  }

  const { simClock } = refs.current;

  return {
    togglePlay: () => simClock.setPlaying(!simClock.isPlaying),
    setMultiplier: (m) => simClock.setMultiplier(m),
    stepBack: () => simClock.step(-300),
    stepForward: () => simClock.step(300),
  };
}
