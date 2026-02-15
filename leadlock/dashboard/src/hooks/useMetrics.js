import { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';

export function useMetrics(period = '7d', pollInterval = 30000) {
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchMetrics = useCallback(async () => {
    try {
      const data = await api.getMetrics(period);
      setMetrics(data);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [period]);

  useEffect(() => {
    setLoading(true);
    fetchMetrics();
    if (pollInterval > 0) {
      const interval = setInterval(fetchMetrics, pollInterval);
      return () => clearInterval(interval);
    }
  }, [fetchMetrics, pollInterval]);

  return { metrics, loading, error, refetch: fetchMetrics };
}
