import { useState, useEffect } from 'react';
import { api } from '../../api/client';
import { Plus, X, Edit2, Trash2, UserCheck } from 'lucide-react';

const STATUSES = ['cold', 'contacted', 'demo_scheduled', 'demo_completed', 'proposal_sent', 'won', 'lost'];

const STATUS_BADGE = {
  cold: 'bg-gray-50 text-gray-600 border border-gray-100',
  contacted: 'bg-amber-50 text-amber-700 border border-amber-100',
  demo_scheduled: 'bg-blue-50 text-blue-700 border border-blue-100',
  demo_completed: 'bg-orange-50 text-orange-700 border border-orange-100',
  proposal_sent: 'bg-orange-50 text-orange-700 border border-orange-100',
  won: 'bg-emerald-50 text-emerald-700 border border-emerald-100',
  lost: 'bg-red-50 text-red-700 border border-red-100',
};

const STATUS_DOT = {
  cold: 'bg-gray-400',
  contacted: 'bg-amber-500',
  demo_scheduled: 'bg-blue-500',
  demo_completed: 'bg-orange-500',
  proposal_sent: 'bg-orange-500',
  won: 'bg-emerald-500',
  lost: 'bg-red-500',
};

const VIEW_MODES = ['board', 'table'];

const inputClasses = 'bg-white border border-gray-200 text-gray-900 outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100 transition-all';

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
    <div style={{ backgroundColor: '#f8f9fb' }}>
      <div className="flex items-center justify-between mb-5">
        <h1 className="text-lg font-semibold tracking-tight text-gray-900">Sales Outreach</h1>
        <div className="flex items-center gap-2">
          <div className="flex gap-1">
            {VIEW_MODES.map(m => (
              <button
                key={m}
                onClick={() => setView(m)}
                className={`px-2.5 py-1 text-xs font-medium rounded-lg capitalize transition-all cursor-pointer ${
                  view === m
                    ? 'bg-orange-50 text-orange-700 border border-orange-200'
                    : 'bg-white text-gray-500 border border-gray-200 hover:border-gray-300 hover:text-gray-700'
                }`}
              >
                {m}
              </button>
            ))}
          </div>
          <button
            onClick={() => { resetForm(); setShowForm(true); }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-white bg-orange-600 hover:bg-orange-700 transition-colors cursor-pointer"
          >
            <Plus className="w-3.5 h-3.5" />
            Add Prospect
          </button>
        </div>
      </div>

      {/* Confirmation Dialog */}
      {confirmAction && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-sm bg-white border border-gray-200 rounded-xl shadow-lg p-6">
            <h2 className="text-base font-semibold text-gray-900 mb-2">
              {confirmAction.type === 'delete' ? 'Delete Prospect' : 'Convert to Client'}
            </h2>
            <p className="text-sm text-gray-500 mb-5">
              {confirmAction.type === 'delete'
                ? `Are you sure you want to delete "${confirmAction.prospect.prospect_name}"? This cannot be undone.`
                : `Convert "${confirmAction.prospect.prospect_name}" into a LeadLock client? This will create a new client account.`
              }
            </p>
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setConfirmAction(null)}
                className="px-3 py-1.5 rounded-lg text-xs font-medium text-gray-500 bg-white border border-gray-200 hover:border-gray-300 transition-colors cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={() => confirmAction.type === 'delete'
                  ? handleDelete(confirmAction.prospect)
                  : handleConvert(confirmAction.prospect)
                }
                className={`px-3 py-1.5 rounded-lg text-xs font-medium text-white transition-colors cursor-pointer ${
                  confirmAction.type === 'delete'
                    ? 'bg-red-500 hover:bg-red-600'
                    : 'bg-emerald-500 hover:bg-emerald-600'
                }`}
              >
                {confirmAction.type === 'delete' ? 'Delete' : 'Convert'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Form Modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-md bg-white border border-gray-200 rounded-xl shadow-lg p-6">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-base font-semibold text-gray-900">
                {editingId ? 'Edit Prospect' : 'New Prospect'}
              </h2>
              <button onClick={resetForm} className="text-gray-400 hover:text-gray-600 cursor-pointer">
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
                  <label className="block text-xs font-medium uppercase tracking-wider text-gray-400 mb-1">{label}</label>
                  <input
                    type={type}
                    value={form[key]}
                    onChange={e => setForm(f => ({ ...f, [key]: e.target.value }))}
                    className={`w-full px-3 py-2 rounded-lg text-sm ${inputClasses}`}
                    placeholder={placeholder}
                  />
                </div>
              ))}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium uppercase tracking-wider text-gray-400 mb-1">Trade Type</label>
                  <select
                    value={form.prospect_trade_type}
                    onChange={e => setForm(f => ({ ...f, prospect_trade_type: e.target.value }))}
                    className={`w-full px-3 py-2 rounded-lg text-sm cursor-pointer ${inputClasses}`}
                  >
                    {['hvac', 'plumbing', 'electrical', 'roofing', 'solar', 'general'].map(t => (
                      <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium uppercase tracking-wider text-gray-400 mb-1">Status</label>
                  <select
                    value={form.status}
                    onChange={e => setForm(f => ({ ...f, status: e.target.value }))}
                    className={`w-full px-3 py-2 rounded-lg text-sm cursor-pointer ${inputClasses}`}
                  >
                    {STATUSES.map(s => (
                      <option key={s} value={s}>{s.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium uppercase tracking-wider text-gray-400 mb-1">Notes</label>
                <textarea
                  value={form.notes}
                  onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
                  className={`w-full px-3 py-2 rounded-lg text-sm resize-none h-20 ${inputClasses}`}
                  placeholder="Notes about the prospect..."
                />
              </div>
              <button
                onClick={handleSave}
                className="w-full py-2.5 rounded-lg text-sm font-medium text-white bg-orange-600 hover:bg-orange-700 transition-colors cursor-pointer"
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
            className={`px-3 py-1.5 rounded-lg text-xs cursor-pointer ${inputClasses}`}
          >
            <option value="">All Statuses</option>
            {STATUSES.map(s => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
          </select>
          <span className="text-xs font-mono text-gray-400">{total} prospects</span>
        </div>
        {totalPages > 1 && (
          <div className="flex items-center gap-1">
            <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}
              className="px-2.5 py-1 text-xs rounded-lg bg-white border border-gray-200 text-gray-600 hover:border-gray-300 disabled:opacity-40 cursor-pointer transition-colors">
              Prev
            </button>
            <span className="px-2 py-1 text-xs font-mono text-gray-500">
              {page} / {totalPages}
            </span>
            <button disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}
              className="px-2.5 py-1 text-xs rounded-lg bg-white border border-gray-200 text-gray-600 hover:border-gray-300 disabled:opacity-40 cursor-pointer transition-colors">
              Next
            </button>
          </div>
        )}
      </div>

      {loading ? (
        <div className="h-64 bg-gray-100 rounded-xl animate-pulse" />
      ) : view === 'board' ? (
        /* Kanban Board */
        <div className="flex gap-2.5 overflow-x-auto pb-4">
          {STATUSES.map(status => (
            <div key={status} className="flex-shrink-0 w-56">
              <div className="flex items-center gap-2 mb-2.5 px-1">
                <span className={`w-2 h-2 rounded-full ${STATUS_DOT[status] || 'bg-gray-400'}`} />
                <span className="text-xs font-medium uppercase tracking-wider text-gray-400">
                  {status.replace('_', ' ')}
                </span>
                <span className="text-[10px] font-mono ml-auto text-gray-400">
                  {grouped[status]?.length || 0}
                </span>
              </div>
              <div className="space-y-2">
                {(grouped[status] || []).map(prospect => (
                  <div
                    key={prospect.id}
                    className="bg-white border border-gray-200 rounded-xl shadow-sm p-3 hover:border-gray-300 transition-colors"
                  >
                    <div className="flex items-start justify-between">
                      <div className="cursor-pointer flex-1" onClick={() => startEdit(prospect)}>
                        <p className="text-sm font-medium text-gray-900">{prospect.prospect_name}</p>
                        <p className="text-xs mt-0.5 text-gray-400">{prospect.prospect_company}</p>
                      </div>
                      <div className="flex items-center gap-0.5 ml-1">
                        {canConvert(prospect) && (
                          <button
                            onClick={(e) => { e.stopPropagation(); setConfirmAction({ type: 'convert', prospect }); }}
                            className="p-1 rounded-md text-emerald-500 hover:bg-emerald-50 transition-colors cursor-pointer"
                            title="Convert to client"
                          >
                            <UserCheck className="w-3 h-3" />
                          </button>
                        )}
                        <button
                          onClick={(e) => { e.stopPropagation(); setConfirmAction({ type: 'delete', prospect }); }}
                          className="p-1 rounded-md text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors cursor-pointer"
                          title="Delete prospect"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </div>
                    </div>
                    <div className="flex items-center justify-between mt-2">
                      <span className="text-xs capitalize text-gray-400">{prospect.prospect_trade_type}</span>
                      {prospect.estimated_mrr && (
                        <span className="text-xs font-mono font-medium text-emerald-600">
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
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100">
                  {['Name', 'Company', 'Trade', 'Status', 'Est. MRR', 'Notes', ''].map(h => (
                    <th key={h} className="text-left px-4 py-2.5 text-xs font-medium uppercase tracking-wider text-gray-500">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {prospects.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-12 text-center text-sm text-gray-400">
                      No prospects yet. Add your first one.
                    </td>
                  </tr>
                ) : prospects.map(prospect => (
                  <tr key={prospect.id} className="border-b border-gray-100 hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-2.5 text-sm font-medium text-gray-900">
                      {prospect.prospect_name}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-gray-500">
                      {prospect.prospect_company || '\u2014'}
                    </td>
                    <td className="px-4 py-2.5 text-xs capitalize text-gray-400">
                      {prospect.prospect_trade_type}
                    </td>
                    <td className="px-4 py-2.5">
                      <select
                        value={prospect.status}
                        onChange={e => updateStatus(prospect.id, e.target.value)}
                        className={`text-xs font-medium px-2 py-0.5 rounded-md cursor-pointer ${STATUS_BADGE[prospect.status] || 'bg-gray-50 text-gray-600 border border-gray-100'}`}
                      >
                        {STATUSES.map(s => (
                          <option key={s} value={s}>{s.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())}</option>
                        ))}
                      </select>
                    </td>
                    <td className={`px-4 py-2.5 text-xs font-mono ${prospect.estimated_mrr ? 'text-emerald-600' : 'text-gray-400'}`}>
                      {prospect.estimated_mrr ? `$${prospect.estimated_mrr}` : '\u2014'}
                    </td>
                    <td className="px-4 py-2.5 text-xs max-w-[200px] truncate text-gray-400">
                      {prospect.notes || '\u2014'}
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => startEdit(prospect)}
                          className="p-1 rounded-md text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors cursor-pointer"
                        >
                          <Edit2 className="w-3.5 h-3.5" />
                        </button>
                        {canConvert(prospect) && (
                          <button
                            onClick={() => setConfirmAction({ type: 'convert', prospect })}
                            className="p-1 rounded-md text-emerald-500 hover:bg-emerald-50 transition-colors cursor-pointer"
                            title="Convert to client"
                          >
                            <UserCheck className="w-3.5 h-3.5" />
                          </button>
                        )}
                        <button
                          onClick={() => setConfirmAction({ type: 'delete', prospect })}
                          className="p-1 rounded-md text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors cursor-pointer"
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
        <div className="mt-4 bg-white border border-gray-200 rounded-xl shadow-sm p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <span className="text-xs font-medium uppercase tracking-wider text-gray-400">Pipeline</span>
              <span className="text-xs font-mono text-gray-500">
                {total} prospects
              </span>
            </div>
            <div className="flex items-center gap-4">
              <span className="text-xs text-gray-400">
                Est. value: <span className="font-mono font-medium text-emerald-600">
                  ${prospects.reduce((sum, p) => sum + (p.estimated_mrr || 0), 0).toLocaleString()}
                </span>/mo
              </span>
              <span className="text-xs text-gray-400">
                Won: <span className="font-mono font-medium text-emerald-600">
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
