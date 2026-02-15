import { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';

export function useLeads(params = {}, pollInterval = 15000) {
  const [leads, setLeads] = useState([]);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchLeads = useCallback(async () => {
    try {
      const data = await api.getLeads(params);
      setLeads(data.leads || []);
      setTotal(data.total || 0);
      setPages(data.pages || 1);
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [JSON.stringify(params)]);

  useEffect(() => {
    setLoading(true);
    fetchLeads();
    if (pollInterval > 0) {
      const interval = setInterval(fetchLeads, pollInterval);
      return () => clearInterval(interval);
    }
  }, [fetchLeads, pollInterval]);

  return { leads, total, pages, loading, error, refetch: fetchLeads };
}
