import { useState, useEffect } from 'react';
import { api } from '../../api/client';
import { Plus, X, Edit2, Trash2, UserCheck } from 'lucide-react';

const STATUSES = ['cold', 'contacted', 'demo_scheduled', 'demo_completed', 'proposal_sent', 'won', 'lost'];
const STATUS_COLORS = {
  cold: '#94a3b8',
  contacted: '#fbbf24',
  demo_scheduled: '#5a72f0',
  demo_completed: '#7c5bf0',
  proposal_sent: '#f59e0b',
  won: '#34d399',
  lost: '#f87171',
};

const VIEW_MODES = ['board', 'table'];

const inputStyle = {
  background: 'var(--surface-2)',
  border: '1px solid var(--border)',
  color: 'var(--text-primary)',
};

export default function AdminOutreach() {
  const [prospects, setProspects] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [statusFilter, setStatusFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState('board');
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [confirmAction, setConfirmAction] = useState(null); // { type: 'delete'|'convert', prospect }
  const [form, setForm] = useState({
    prospect_name: '', prospect_company: '', prospect_email: '', prospect_phone: '',
    prospect_trade_type: 'hvac', status: 'cold', notes: '', estimated_mrr: '',
  });

  const fetchOutreach = async () => {
    try {
      const params = { page, per_page: 50 };
      if (statusFilter) params.status = statusFilter;
      const data = await api.getAdminOutreach(params);
      setProspects(data.prospects || []);
      setTotal(data.total || 0);
      setTotalPages(data.pages || 1);
    } catch (e) {
      console.error('Failed to fetch outreach:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchOutreach(); }, [page, statusFilter]);

  const resetForm = () => {
    setForm({
      prospect_name: '', prospect_company: '', prospect_email: '', prospect_phone: '',
      prospect_trade_type: 'hvac', status: 'cold', notes: '', estimated_mrr: '',
    });
    setShowForm(false);
    setEditingId(null);
  };

  const handleSave = async () => {
    try {
      const payload = { ...form, estimated_mrr: form.estimated_mrr ? Number(form.estimated_mrr) : null };
      if (editingId) {
        await api.updateOutreach(editingId, payload);
      } else {
        await api.createOutreach(payload);
      }
      resetForm();
      fetchOutreach();
    } catch (e) {
      console.error('Failed to save prospect:', e);
    }
  };

  const startEdit = (prospect) => {
    setForm({
      prospect_name: prospect.prospect_name || '',
      prospect_company: prospect.prospect_company || '',
      prospect_email: prospect.prospect_email || '',
      prospect_phone: prospect.prospect_phone || '',
      prospect_trade_type: prospect.prospect_trade_type || 'hvac',
      status: prospect.status || 'cold',
      notes: prospect.notes || '',
      estimated_mrr: prospect.estimated_mrr?.toString() || '',
    });
    setEditingId(prospect.id);
    setShowForm(true);
  };

  const updateStatus = async (id, newStatus) => {
    try {
      await api.updateOutreach(id, { status: newStatus });
      fetchOutreach();
    } catch (e) {
      console.error('Failed to update status:', e);
    }
  };

  const handleDelete = async (prospect) => {
    try {
      await api.deleteOutreach(prospect.id);
      setConfirmAction(null);
      fetchOutreach();
    } catch (e) {
      console.error('Failed to delete prospect:', e);
    }
  };

  const handleConvert = async (prospect) => {
    try {
      await api.convertOutreach(prospect.id);
      setConfirmAction(null);
      fetchOutreach();
    } catch (e) {
      console.error('Failed to convert prospect:', e);
    }
  };

  const canConvert = (prospect) =>
    ['won', 'proposal_sent'].includes(prospect.status) && !prospect.converted_client_id;

  const grouped = STATUSES.reduce((acc, s) => {
    acc[s] = prospects.filter(p => p.status === s);
    return acc;
  }, {});

  return (
    <div className="animate-fade-up">
      <div className="flex items-center justify-between mb-5">
        <h1 className="text-lg font-semibold tracking-tight" style={{ color: 'var(--text-primary)' }}>Sales Outreach</h1>
        <div className="flex items-center gap-2">
          <div className="flex gap-1">
            {VIEW_MODES.map(m => (
              <button
                key={m}
                onClick={() => setView(m)}
                className="px-2.5 py-1 text-[11px] font-medium rounded-md capitalize transition-all"
                style={{
                  background: view === m ? 'var(--accent-muted)' : 'transparent',
                  color: view === m ? 'var(--accent)' : 'var(--text-tertiary)',
                  border: view === m ? '1px solid rgba(124, 91, 240, 0.2)' : '1px solid var(--border)',
                }}
              >
                {m}
              </button>
            ))}
          </div>
          <button
            onClick={() => { resetForm(); setShowForm(true); }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[12px] font-semibold text-white transition-all gradient-btn"
          >
            <Plus className="w-3.5 h-3.5" />
            Add Prospect
          </button>
        </div>
      </div>

      {/* Confirmation Dialog */}
      {confirmAction && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-sm rounded-xl p-6 glass-card gradient-border">
            <h2 className="text-[15px] font-semibold mb-2" style={{ color: 'var(--text-primary)' }}>
              {confirmAction.type === 'delete' ? 'Delete Prospect' : 'Convert to Client'}
            </h2>
            <p className="text-[13px] mb-5" style={{ color: 'var(--text-secondary)' }}>
              {confirmAction.type === 'delete'
                ? `Are you sure you want to delete "${confirmAction.prospect.prospect_name}"? This cannot be undone.`
                : `Convert "${confirmAction.prospect.prospect_name}" into a LeadLock client? This will create a new client account.`
              }
            </p>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setConfirmAction(null)}
                className="px-3 py-1.5 rounded-md text-[12px] font-medium transition-all"
                style={{ color: 'var(--text-tertiary)', border: '1px solid var(--border)' }}
              >
                Cancel
              </button>
              <button
                onClick={() => confirmAction.type === 'delete'
                  ? handleDelete(confirmAction.prospect)
                  : handleConvert(confirmAction.prospect)
                }
                className="px-3 py-1.5 rounded-md text-[12px] font-medium text-white transition-all"
                style={{ background: confirmAction.type === 'delete' ? '#f87171' : '#34d399' }}
              >
                {confirmAction.type === 'delete' ? 'Delete' : 'Convert'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Form Modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-xl p-6 glass-card gradient-border">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-[15px] font-semibold" style={{ color: 'var(--text-primary)' }}>
                {editingId ? 'Edit Prospect' : 'New Prospect'}
              </h2>
              <button onClick={resetForm} style={{ color: 'var(--text-tertiary)' }}>
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="space-y-3">
              {[
                { label: 'Name', key: 'prospect_name', type: 'text', placeholder: 'John Smith' },
                { label: 'Company', key: 'prospect_company', type: 'text', placeholder: 'Smith Plumbing' },
                { label: 'Email', key: 'prospect_email', type: 'email', placeholder: 'john@smithplumbing.com' },
                { label: 'Phone', key: 'prospect_phone', type: 'text', placeholder: '+15551234567' },
                { label: 'Est. MRR', key: 'estimated_mrr', type: 'number', placeholder: '997' },
              ].map(({ label, key, type, placeholder }) => (
                <div key={key}>
                  <label className="block text-[11px] font-medium uppercase tracking-wider mb-1" style={{ color: 'var(--text-tertiary)' }}>{label}</label>
                  <input
                    type={type}
                    value={form[key]}
                    onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
                    className="w-full px-3 py-2 rounded-md text-[13px] outline-none"
                    style={inputStyle}
                    placeholder={placeholder}
                  />
                </div>
              ))}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-medium uppercase tracking-wider mb-1" style={{ color: 'var(--text-tertiary)' }}>Trade Type</label>
                  <select
                    value={form.prospect_trade_type}
                    onChange={e => setForm(f => ({ ...f, prospect_trade_type: e.target.value }))}
                    className="w-full px-3 py-2 rounded-md text-[13px] outline-none"
                    style={inputStyle}
                  >
                    {['hvac', 'plumbing', 'electrical', 'roofing', 'solar', 'general'].map(t => (
                      <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] font-medium uppercase tracking-wider mb-1" style={{ color: 'var(--text-tertiary)' }}>Status</label>
                  <select
                    value={form.status}
                    onChange={e => setForm(f => ({ ...f, status: e.target.value }))}
                    className="w-full px-3 py-2 rounded-md text-[13px] outline-none"
                    style={inputStyle}
                  >
                    {STATUSES.map(s => (
                      <option key={s} value={s}>{s.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-[11px] font-medium uppercase tracking-wider mb-1" style={{ color: 'var(--text-tertiary)' }}>Notes</label>
                <textarea
                  value={form.notes}
                  onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
                  className="w-full px-3 py-2 rounded-md text-[13px] outline-none resize-none h-20"
                  style={inputStyle}
                  placeholder="Notes about the prospect..."
                />
              </div>
              <button
                onClick={handleSave}
                className="w-full py-2.5 rounded-md text-[13px] font-medium text-white transition-all"
                style={{ background: 'var(--accent)' }}
              >
                {editingId ? 'Update Prospect' : 'Create Prospect'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Filters & Pagination */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <select
            value={statusFilter}
            onChange={e => { setStatusFilter(e.target.value); setPage(1); }}
            className="px-3 py-1.5 rounded-md text-[12px] outline-none"
            style={inputStyle}
          >
            <option value="">All Statuses</option>
            {STATUSES.map(s => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
          </select>
          <span className="text-[12px] font-mono" style={{ color: 'var(--text-tertiary)' }}>{total} prospects</span>
        </div>
        {totalPages > 1 && (
          <div className="flex items-center gap-1">
            <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}
              className="px-2 py-1 text-[11px] rounded disabled:opacity-40" style={inputStyle}>Prev</button>
            <span className="px-2 py-1 text-[11px] font-mono" style={{ color: 'var(--text-secondary)' }}>
              {page} / {totalPages}
            </span>
            <button disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}
              className="px-2 py-1 text-[11px] rounded disabled:opacity-40" style={inputStyle}>Next</button>
          </div>
        )}
      </div>

      {loading ? (
        <div className="h-64 rounded-card animate-pulse" style={{ background: 'var(--surface-1)' }} />
      ) : view === 'board' ? (
        /* Kanban Board */
        <div className="flex gap-2.5 overflow-x-auto pb-4">
          {STATUSES.map(status => (
            <div key={status} className="flex-shrink-0 w-56">
              <div className="flex items-center gap-2 mb-2.5 px-1">
                <span className="w-2 h-2 rounded-full" style={{ background: STATUS_COLORS[status] }} />
                <span className="text-[11px] font-medium uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>
                  {status.replace('_', ' ')}
                </span>
                <span className="text-[10px] font-mono ml-auto" style={{ color: 'var(--text-tertiary)' }}>
                  {grouped[status]?.length || 0}
                </span>
              </div>
              <div className="space-y-2">
                {(grouped[status] || []).map(prospect => (
                  <div
                    key={prospect.id}
                    className="glass-card p-3"
                  >
                    <div className="flex items-start justify-between">
                      <div className="cursor-pointer flex-1" onClick={() => startEdit(prospect)}>
                        <p className="text-[13px] font-medium" style={{ color: 'var(--text-primary)' }}>{prospect.prospect_name}</p>
                        <p className="text-[11px] mt-0.5" style={{ color: 'var(--text-tertiary)' }}>{prospect.prospect_company}</p>
                      </div>
                      <div className="flex items-center gap-0.5 ml-1">
                        {canConvert(prospect) && (
                          <button
                            onClick={(e) => { e.stopPropagation(); setConfirmAction({ type: 'convert', prospect }); }}
                            className="p-1 rounded transition-colors"
                            style={{ color: '#34d399' }}
                            title="Convert to client"
                          >
                            <UserCheck className="w-3 h-3" />
                          </button>
                        )}
                        <button
                          onClick={(e) => { e.stopPropagation(); setConfirmAction({ type: 'delete', prospect }); }}
                          className="p-1 rounded transition-colors"
                          style={{ color: 'var(--text-tertiary)' }}
                          onMouseEnter={e => e.currentTarget.style.color = '#f87171'}
                          onMouseLeave={e => e.currentTarget.style.color = 'var(--text-tertiary)'}
                          title="Delete prospect"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </div>
                    </div>
                    <div className="flex items-center justify-between mt-2">
                      <span className="text-[11px] capitalize" style={{ color: 'var(--text-tertiary)' }}>{prospect.prospect_trade_type}</span>
                      {prospect.estimated_mrr && (
                        <span className="text-[11px] font-mono font-medium" style={{ color: '#34d399' }}>
                          ${prospect.estimated_mrr}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        /* Table View */
        <div className="glass-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)', background: 'rgba(255, 255, 255, 0.02)' }}>
                  {['Name', 'Company', 'Trade', 'Status', 'Est. MRR', 'Notes', ''].map(h => (
                    <th key={h} className="text-left px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {prospects.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-12 text-center text-[13px]" style={{ color: 'var(--text-tertiary)' }}>
                      No prospects yet. Add your first one.
                    </td>
                  </tr>
                ) : prospects.map(prospect => (
                  <tr key={prospect.id} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td className="px-4 py-2.5 text-[13px] font-medium" style={{ color: 'var(--text-primary)' }}>
                      {prospect.prospect_name}
                    </td>
                    <td className="px-4 py-2.5 text-[12px]" style={{ color: 'var(--text-secondary)' }}>
                      {prospect.prospect_company || '—'}
                    </td>
                    <td className="px-4 py-2.5 text-[12px] capitalize" style={{ color: 'var(--text-tertiary)' }}>
                      {prospect.prospect_trade_type}
                    </td>
                    <td className="px-4 py-2.5">
                      <select
                        value={prospect.status}
                        onChange={e => updateStatus(prospect.id, e.target.value)}
                        className="text-[11px] font-medium px-1.5 py-0.5 rounded outline-none cursor-pointer"
                        style={{
                          color: STATUS_COLORS[prospect.status],
                          background: `${STATUS_COLORS[prospect.status]}15`,
                          border: 'none',
                        }}
                      >
                        {STATUSES.map(s => (
                          <option key={s} value={s}>{s.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())}</option>
                        ))}
                      </select>
                    </td>
                    <td className="px-4 py-2.5 text-[12px] font-mono" style={{ color: prospect.estimated_mrr ? '#34d399' : 'var(--text-tertiary)' }}>
                      {prospect.estimated_mrr ? `$${prospect.estimated_mrr}` : '—'}
                    </td>
                    <td className="px-4 py-2.5 text-[11px] max-w-[200px] truncate" style={{ color: 'var(--text-tertiary)' }}>
                      {prospect.notes || '—'}
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => startEdit(prospect)}
                          className="p-1 rounded transition-colors"
                          style={{ color: 'var(--text-tertiary)' }}
                          onMouseEnter={e => e.currentTarget.style.color = 'var(--text-primary)'}
                          onMouseLeave={e => e.currentTarget.style.color = 'var(--text-tertiary)'}
                        >
                          <Edit2 className="w-3.5 h-3.5" />
                        </button>
                        {canConvert(prospect) && (
                          <button
                            onClick={() => setConfirmAction({ type: 'convert', prospect })}
                            className="p-1 rounded transition-colors"
                            style={{ color: '#34d399' }}
                            title="Convert to client"
                          >
                            <UserCheck className="w-3.5 h-3.5" />
                          </button>
                        )}
                        <button
                          onClick={() => setConfirmAction({ type: 'delete', prospect })}
                          className="p-1 rounded transition-colors"
                          style={{ color: 'var(--text-tertiary)' }}
                          onMouseEnter={e => e.currentTarget.style.color = '#f87171'}
                          onMouseLeave={e => e.currentTarget.style.color = 'var(--text-tertiary)'}
                          title="Delete prospect"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Pipeline summary */}
      {!loading && prospects.length > 0 && (
        <div className="mt-4 glass-card gradient-border p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <span className="text-[11px] font-medium uppercase tracking-wider" style={{ color: 'var(--text-tertiary)' }}>Pipeline</span>
              <span className="text-[12px] font-mono" style={{ color: 'var(--text-secondary)' }}>
                {total} prospects
              </span>
            </div>
            <div className="flex items-center gap-4">
              <span className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>
                Est. value: <span className="font-mono font-medium" style={{ color: '#34d399' }}>
                  ${prospects.reduce((sum, p) => sum + (p.estimated_mrr || 0), 0).toLocaleString()}
                </span>/mo
              </span>
              <span className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>
                Won: <span className="font-mono font-medium" style={{ color: '#34d399' }}>
                  {prospects.filter(p => p.status === 'won').length}
                </span>
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
