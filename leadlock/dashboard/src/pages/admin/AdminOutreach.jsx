import { useState, useEffect } from 'react';
import { api } from '../../api/client';
import { Plus, X, Edit2, Trash2, UserCheck } from 'lucide-react';
import PageHeader from '../../components/ui/PageHeader';
import Badge from '../../components/ui/Badge';
import DataTable from '../../components/ui/DataTable';
import EmptyState from '../../components/ui/EmptyState';
import StatusDot from '../../components/ui/StatusDot';

const STATUSES = ['cold', 'contacted', 'demo_scheduled', 'demo_completed', 'proposal_sent', 'won', 'lost'];

const STATUS_VARIANT = {
  cold: 'neutral',
  contacted: 'warning',
  demo_scheduled: 'info',
  demo_completed: 'info',
  proposal_sent: 'warning',
  won: 'success',
  lost: 'danger',
};

const STATUS_DOT_COLOR = {
  cold: 'gray',
  contacted: 'yellow',
  demo_scheduled: 'yellow',
  demo_completed: 'yellow',
  proposal_sent: 'yellow',
  won: 'green',
  lost: 'red',
};

const VIEW_MODES = ['board', 'table'];

const INPUT_CLASSES = 'bg-white border border-gray-200 text-gray-900 outline-none focus:border-orange-400 focus:ring-2 focus:ring-orange-100 transition-all';

function formatStatus(status) {
  return (status || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function ConfirmDialog({ action, onCancel, onConfirm }) {
  if (!action) return null;

  const isDelete = action.type === 'delete';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-sm bg-white border border-gray-200/50 rounded-2xl shadow-lg p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-2">
          {isDelete ? 'Delete Prospect' : 'Convert to Client'}
        </h2>
        <p className="text-sm text-gray-600 mb-6">
          {isDelete
            ? `Are you sure you want to delete "${action.prospect.prospect_name}"? This cannot be undone.`
            : `Convert "${action.prospect.prospect_name}" into a LeadLock client? This will create a new client account.`
          }
        </p>
        <div className="flex gap-2 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-2 rounded-xl text-sm font-medium text-gray-600 bg-white border border-gray-200 hover:border-gray-300 transition-colors cursor-pointer"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className={`px-4 py-2 rounded-xl text-sm font-medium text-white transition-colors cursor-pointer ${
              isDelete
                ? 'bg-red-500 hover:bg-red-600'
                : 'bg-emerald-500 hover:bg-emerald-600'
            }`}
          >
            {isDelete ? 'Delete' : 'Convert'}
          </button>
        </div>
      </div>
    </div>
  );
}

function ProspectFormModal({ show, editingId, form, onFormChange, onSave, onClose }) {
  if (!show) return null;

  const fields = [
    { label: 'Name', key: 'prospect_name', type: 'text', placeholder: 'John Smith' },
    { label: 'Company', key: 'prospect_company', type: 'text', placeholder: 'Smith Plumbing' },
    { label: 'Email', key: 'prospect_email', type: 'email', placeholder: 'john@smithplumbing.com' },
    { label: 'Phone', key: 'prospect_phone', type: 'text', placeholder: '+15551234567' },
    { label: 'Est. MRR', key: 'estimated_mrr', type: 'number', placeholder: '997' },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md bg-white border border-gray-200/50 rounded-2xl shadow-lg p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-semibold text-gray-900">
            {editingId ? 'Edit Prospect' : 'New Prospect'}
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 cursor-pointer">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="space-y-4">
          {fields.map(({ label, key, type, placeholder }) => (
            <div key={key}>
              <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">{label}</label>
              <input
                type={type}
                value={form[key]}
                onChange={(e) => onFormChange({ ...form, [key]: e.target.value })}
                className={`w-full px-3 py-2.5 rounded-xl text-sm ${INPUT_CLASSES}`}
                placeholder={placeholder}
              />
            </div>
          ))}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">Trade Type</label>
              <select
                value={form.prospect_trade_type}
                onChange={(e) => onFormChange({ ...form, prospect_trade_type: e.target.value })}
                className={`w-full px-3 py-2.5 rounded-xl text-sm cursor-pointer ${INPUT_CLASSES}`}
              >
                {['hvac', 'plumbing', 'electrical', 'roofing', 'solar', 'general'].map((t) => (
                  <option key={t} value={t}>{t.charAt(0).toUpperCase() + t.slice(1)}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">Status</label>
              <select
                value={form.status}
                onChange={(e) => onFormChange({ ...form, status: e.target.value })}
                className={`w-full px-3 py-2.5 rounded-xl text-sm cursor-pointer ${INPUT_CLASSES}`}
              >
                {STATUSES.map((s) => (
                  <option key={s} value={s}>{formatStatus(s)}</option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">Notes</label>
            <textarea
              value={form.notes}
              onChange={(e) => onFormChange({ ...form, notes: e.target.value })}
              className={`w-full px-3 py-2.5 rounded-xl text-sm resize-none h-20 ${INPUT_CLASSES}`}
              placeholder="Notes about the prospect..."
            />
          </div>
          <button
            onClick={onSave}
            className="w-full py-2.5 rounded-xl text-sm font-medium text-white bg-orange-500 hover:bg-orange-600 transition-colors cursor-pointer"
          >
            {editingId ? 'Update Prospect' : 'Create Prospect'}
          </button>
        </div>
      </div>
    </div>
  );
}

function KanbanBoard({ grouped, onEdit, onDelete, onConvert, canConvert }) {
  return (
    <div className="flex gap-3 overflow-x-auto pb-4">
      {STATUSES.map((status) => (
        <div key={status} className="flex-shrink-0 w-60">
          <div className="flex items-center gap-2 mb-3 px-1">
            <StatusDot color={STATUS_DOT_COLOR[status] || 'gray'} />
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">
              {formatStatus(status)}
            </span>
            <span className="text-xs font-mono ml-auto text-gray-400">
              {grouped[status]?.length || 0}
            </span>
          </div>
          <div className="space-y-2">
            {(grouped[status] || []).map((prospect) => (
              <div
                key={prospect.id}
                className="bg-white border border-gray-200/50 rounded-xl p-4 shadow-card cursor-pointer hover:border-gray-300 transition-colors"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1" onClick={() => onEdit(prospect)}>
                    <p className="text-sm font-medium text-gray-900">{prospect.prospect_name}</p>
                    <p className="text-xs mt-0.5 text-gray-400">{prospect.prospect_company}</p>
                    {prospect.prospect_phone && (
                      <p className="text-xs font-mono text-gray-400 mt-1">{prospect.prospect_phone}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-0.5 ml-2">
                    {canConvert(prospect) && (
                      <button
                        onClick={(e) => { e.stopPropagation(); onConvert(prospect); }}
                        className="p-1 rounded-lg text-emerald-500 hover:bg-emerald-50 transition-colors cursor-pointer"
                        title="Convert to client"
                      >
                        <UserCheck className="w-3.5 h-3.5" />
                      </button>
                    )}
                    <button
                      onClick={(e) => { e.stopPropagation(); onDelete(prospect); }}
                      className="p-1 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors cursor-pointer"
                      title="Delete prospect"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
                <div className="flex items-center justify-between mt-3">
                  <Badge variant={STATUS_VARIANT[prospect.status] || 'neutral'} size="sm">
                    {prospect.prospect_trade_type}
                  </Badge>
                  {prospect.estimated_mrr && (
                    <span className="text-xs font-mono font-medium text-emerald-600">
                      ${prospect.estimated_mrr}
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-400 mt-2">
                  {prospect.created_at
                    ? new Date(prospect.created_at).toLocaleDateString([], { month: 'short', day: 'numeric' })
                    : ''}
                </p>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function ProspectTableView({ prospects, onEdit, onDelete, onConvert, canConvert, onStatusChange }) {
  const columns = [
    {
      key: 'prospect_name',
      label: 'Name',
      render: (val) => <span className="font-medium text-gray-900">{val}</span>,
    },
    {
      key: 'prospect_company',
      label: 'Company',
      render: (val) => <span className="text-gray-500">{val || '\u2014'}</span>,
    },
    {
      key: 'prospect_trade_type',
      label: 'Trade',
      render: (val) => <span className="text-gray-500 capitalize">{val}</span>,
    },
    {
      key: 'status',
      label: 'Status',
      render: (val, row) => (
        <select
          value={val}
          onChange={(e) => { e.stopPropagation(); onStatusChange(row.id, e.target.value); }}
          className="text-xs font-medium px-2 py-0.5 rounded-lg cursor-pointer bg-white border border-gray-200 text-gray-700 focus:border-orange-400 focus:ring-1 focus:ring-orange-100 outline-none"
          onClick={(e) => e.stopPropagation()}
        >
          {STATUSES.map((s) => (
            <option key={s} value={s}>{formatStatus(s)}</option>
          ))}
        </select>
      ),
    },
    {
      key: 'estimated_mrr',
      label: 'Est. MRR',
      align: 'right',
      render: (val) => (
        <span className={`font-mono ${val ? 'text-emerald-600' : 'text-gray-400'}`}>
          {val ? `$${val}` : '\u2014'}
        </span>
      ),
    },
    {
      key: 'notes',
      label: 'Notes',
      render: (val) => <span className="text-gray-400 truncate max-w-[200px] block">{val || '\u2014'}</span>,
    },
    {
      key: '_actions',
      label: '',
      render: (_, row) => (
        <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
          <button
            onClick={() => onEdit(row)}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors cursor-pointer"
          >
            <Edit2 className="w-3.5 h-3.5" />
          </button>
          {canConvert(row) && (
            <button
              onClick={() => onConvert(row)}
              className="p-1.5 rounded-lg text-emerald-500 hover:bg-emerald-50 transition-colors cursor-pointer"
              title="Convert to client"
            >
              <UserCheck className="w-3.5 h-3.5" />
            </button>
          )}
          <button
            onClick={() => onDelete(row)}
            className="p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors cursor-pointer"
            title="Delete prospect"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      ),
    },
  ];

  return (
    <DataTable
      columns={columns}
      data={prospects}
      emptyMessage="No prospects yet. Add your first one."
    />
  );
}

function PipelineSummary({ prospects, total }) {
  const estimatedValue = prospects.reduce((sum, p) => sum + (p.estimated_mrr || 0), 0);
  const wonCount = prospects.filter((p) => p.status === 'won').length;

  return (
    <div className="bg-white border border-gray-200/50 rounded-2xl p-5 shadow-card">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">Pipeline</span>
          <span className="text-xs font-mono text-gray-500">{total} prospects</span>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-xs text-gray-400">
            Est. value: <span className="font-mono font-medium text-emerald-600">
              ${estimatedValue.toLocaleString()}
            </span>/mo
          </span>
          <span className="text-xs text-gray-400">
            Won: <span className="font-mono font-medium text-emerald-600">{wonCount}</span>
          </span>
        </div>
      </div>
    </div>
  );
}

const EMPTY_FORM = {
  prospect_name: '', prospect_company: '', prospect_email: '', prospect_phone: '',
  prospect_trade_type: 'hvac', status: 'cold', notes: '', estimated_mrr: '',
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
  const [confirmAction, setConfirmAction] = useState(null);
  const [form, setForm] = useState({ ...EMPTY_FORM });

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
    setForm({ ...EMPTY_FORM });
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
    acc[s] = prospects.filter((p) => p.status === s);
    return acc;
  }, {});

  return (
    <div className="min-h-screen bg-[#FAFAFA]">
      <PageHeader
        title="Sales Outreach"
        actions={
          <div className="flex items-center gap-2">
            <div className="flex gap-1 bg-gray-100 rounded-xl p-0.5">
              {VIEW_MODES.map((m) => (
                <button
                  key={m}
                  onClick={() => setView(m)}
                  className={`px-3 py-1.5 text-xs font-medium rounded-lg capitalize transition-all cursor-pointer ${
                    view === m
                      ? 'bg-white text-gray-900 shadow-sm'
                      : 'text-gray-500 hover:text-gray-700'
                  }`}
                >
                  {m}
                </button>
              ))}
            </div>
            <button
              onClick={() => { resetForm(); setShowForm(true); }}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-medium text-white bg-orange-500 hover:bg-orange-600 transition-colors cursor-pointer"
            >
              <Plus className="w-4 h-4" />
              New Prospect
            </button>
          </div>
        }
      />

      <ConfirmDialog
        action={confirmAction}
        onCancel={() => setConfirmAction(null)}
        onConfirm={() =>
          confirmAction.type === 'delete'
            ? handleDelete(confirmAction.prospect)
            : handleConvert(confirmAction.prospect)
        }
      />

      <ProspectFormModal
        show={showForm}
        editingId={editingId}
        form={form}
        onFormChange={setForm}
        onSave={handleSave}
        onClose={resetForm}
      />

      {/* Filters & Pagination */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }}
            className={`px-3 py-2 rounded-xl text-sm cursor-pointer ${INPUT_CLASSES}`}
          >
            <option value="">All Statuses</option>
            {STATUSES.map((s) => <option key={s} value={s}>{formatStatus(s)}</option>)}
          </select>
          <span className="text-xs font-mono text-gray-400">{total} prospects</span>
        </div>
        {totalPages > 1 && (
          <div className="flex items-center gap-1">
            <button
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
              className="px-3 py-1.5 text-xs font-medium rounded-xl bg-white border border-gray-200 text-gray-600 hover:border-gray-300 disabled:opacity-40 cursor-pointer transition-colors"
            >
              Prev
            </button>
            <span className="px-2.5 py-1.5 text-xs font-mono text-gray-500">
              {page} / {totalPages}
            </span>
            <button
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
              className="px-3 py-1.5 text-xs font-medium rounded-xl bg-white border border-gray-200 text-gray-600 hover:border-gray-300 disabled:opacity-40 cursor-pointer transition-colors"
            >
              Next
            </button>
          </div>
        )}
      </div>

      {loading ? (
        <div className="h-64 bg-gray-100 rounded-2xl animate-pulse" />
      ) : view === 'board' ? (
        <KanbanBoard
          grouped={grouped}
          onEdit={startEdit}
          onDelete={(p) => setConfirmAction({ type: 'delete', prospect: p })}
          onConvert={(p) => setConfirmAction({ type: 'convert', prospect: p })}
          canConvert={canConvert}
        />
      ) : (
        <ProspectTableView
          prospects={prospects}
          onEdit={startEdit}
          onDelete={(p) => setConfirmAction({ type: 'delete', prospect: p })}
          onConvert={(p) => setConfirmAction({ type: 'convert', prospect: p })}
          canConvert={canConvert}
          onStatusChange={updateStatus}
        />
      )}

      {!loading && prospects.length > 0 && (
        <div className="mt-5">
          <PipelineSummary prospects={prospects} total={total} />
        </div>
      )}
    </div>
  );
}
