import { useState, useEffect, useRef, useCallback } from 'react';
import { api } from '../api/client';

const POLL_INTERVAL_MS = 30_000;

/**
 * Polls GET /api/v1/agents/system-map every 30 seconds.
 * Returns { data, loading, error }.
 */
export default function useSystemMap() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const intervalRef = useRef(null);
  const isFirstLoad = useRef(true);

  const fetchMap = useCallback(async () => {
    try {
      const res = await api.getSystemMap();
      setData(res.data);
      setError(null);
    } catch (err) {
      setError(err.message || 'Failed to load system map');
    } finally {
      if (isFirstLoad.current) {
        setLoading(false);
        isFirstLoad.current = false;
      }
    }
  }, []);

  useEffect(() => {
    fetchMap();
    intervalRef.current = setInterval(fetchMap, POLL_INTERVAL_MS);
    return () => clearInterval(intervalRef.current);
  }, [fetchMap]);

  return { data, loading, error };
}
