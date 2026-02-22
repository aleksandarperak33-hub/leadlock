import { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '../api/client';

const POLL_INTERVAL_MS = 10_000;

/**
 * Polls GET /api/v1/agents/fleet every 10 seconds.
 * Returns { data, loading, error, refresh }.
 * First fetch sets loading=true; subsequent polls update data silently.
 */
export default function useAgentFleet() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const intervalRef = useRef(null);
  const isFirstLoad = useRef(true);

  const fetchFleet = useCallback(async () => {
    try {
      const res = await api.getAgentFleet();
      setData(res.data);
      setError(null);
    } catch (err) {
      setError(err.message || 'Failed to load agent fleet');
    } finally {
      if (isFirstLoad.current) {
        setLoading(false);
        isFirstLoad.current = false;
      }
    }
  }, []);

  useEffect(() => {
    fetchFleet();
    intervalRef.current = setInterval(fetchFleet, POLL_INTERVAL_MS);
    return () => clearInterval(intervalRef.current);
  }, [fetchFleet]);

  return { data, loading, error, refresh: fetchFleet };
}
