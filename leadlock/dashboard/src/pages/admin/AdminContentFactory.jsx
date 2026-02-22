import { useState, useEffect } from 'react';
import { FileText, Check, X, Copy, Trash2, AlertCircle } from 'lucide-react';
import { api } from '../../api/client';
import PageHeader from '../../components/ui/PageHeader';
import Badge from '../../components/ui/Badge';
import EmptyState from '../../components/ui/EmptyState';

const STATUS_TABS = ['All', 'Draft', 'Approved', 'Published', 'Rejected'];
const TYPE_OPTIONS = ['All', 'blog_post', 'twitter', 'linkedin', 'reddit', 'lead_magnet'];

const STATUS_VARIANT = {
  draft: 'neutral',
  approved: 'success',
  published: 'info',
  rejected: 'danger',
};

const TYPE_VARIANT = {
  blog_post: 'info',
  twitter: 'info',
  linkedin: 'info',
  reddit: 'warning',
  lead_magnet: 'success',
};

function ContentCard({ piece, onStatusChange, onDelete }) {
  const [actionLoading, setActionLoading] = useState(null);
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(piece.body || '');
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleStatus = async (status) => {
    setActionLoading(status);
    try {
      await api.updateContentStatus(piece.id, status);
      onStatusChange(piece.id, status);
    } catch {
      // error handled by parent state not changing
    } finally {
      setActionLoading(null);
    }
  };

  const handleDelete = async () => {
    setActionLoading('delete');
    try {
      await api.deleteContentPiece(piece.id);
      onDelete(piece.id);
    } catch {
      setActionLoading(null);
    }
  };

  const preview = (piece.body || '').slice(0, 200);

  return (
    <div className="bg-white border border-gray-200/60 rounded-2xl p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-gray-900 truncate">{piece.title || 'Untitled'}</h3>
          <p className="text-xs text-gray-400 mt-0.5">
            {piece.word_count ? `${piece.word_count} words` : ''}{piece.cost != null ? ` · $${Number(piece.cost).toFixed(4)}` : ''}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Badge variant={TYPE_VARIANT[piece.content_type] || 'neutral'}>{piece.content_type}</Badge>
          <Badge variant={STATUS_VARIANT[piece.status] || 'neutral'}>{piece.status}</Badge>
        </div>
      </div>

      <p className="text-sm text-gray-600 leading-relaxed mb-4">
        {preview}{(piece.body || '').length > 200 ? '…' : ''}
      </p>

      <div className="flex items-center gap-2 flex-wrap">
        {piece.status !== 'approved' && (
          <button
            onClick={() => handleStatus('approved')}
            disabled={!!actionLoading}
            className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-emerald-50 text-emerald-700 hover:bg-emerald-100 disabled:opacity-50 cursor-pointer"
          >
            <Check className="w-3.5 h-3.5" />
            {actionLoading === 'approved' ? 'Approving…' : 'Approve'}
          </button>
        )}
        {piece.status !== 'rejected' && (
          <button
            onClick={() => handleStatus('rejected')}
            disabled={!!actionLoading}
            className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-red-50 text-red-700 hover:bg-red-100 disabled:opacity-50 cursor-pointer"
          >
            <X className="w-3.5 h-3.5" />
            {actionLoading === 'rejected' ? 'Rejecting…' : 'Reject'}
          </button>
        )}
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-gray-100 text-gray-600 hover:bg-gray-200 cursor-pointer"
        >
          <Copy className="w-3.5 h-3.5" />
          {copied ? 'Copied!' : 'Copy'}
        </button>
        <button
          onClick={handleDelete}
          disabled={!!actionLoading}
          className="flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-lg bg-gray-100 text-gray-500 hover:bg-red-50 hover:text-red-600 disabled:opacity-50 cursor-pointer ml-auto"
        >
          <Trash2 className="w-3.5 h-3.5" />
          {actionLoading === 'delete' ? 'Deleting…' : 'Delete'}
        </button>
      </div>
    </div>
  );
}

export default function AdminContentFactory() {
  const [pieces, setPieces] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState('All');
  const [typeFilter, setTypeFilter] = useState('All');

  useEffect(() => {
    loadPieces();
  }, []);

  const loadPieces = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getContentPieces();
      setPieces(Array.isArray(data) ? data : (data.items || []));
    } catch (err) {
      setError(err.message || 'Failed to load content pieces.');
    } finally {
      setLoading(false);
    }
  };

  const handleStatusChange = (id, newStatus) => {
    setPieces((prev) =>
      prev.map((p) => (p.id === id ? { ...p, status: newStatus } : p))
    );
  };

  const handleDelete = (id) => {
    setPieces((prev) => prev.filter((p) => p.id !== id));
  };

  const filtered = pieces.filter((p) => {
    const matchStatus = statusFilter === 'All' || p.status === statusFilter.toLowerCase();
    const matchType = typeFilter === 'All' || p.content_type === typeFilter;
    return matchStatus && matchType;
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#FAFAFA]">
      <PageHeader
        title="Content Factory"
        subtitle={`${pieces.length} content piece${pieces.length !== 1 ? 's' : ''}`}
      />

      {error && (
        <div className="mb-4 flex items-center gap-3 px-4 py-3 rounded-xl bg-red-50 border border-red-200/60">
          <AlertCircle className="w-4 h-4 text-red-500 shrink-0" />
          <p className="text-sm text-red-700 flex-1">{error}</p>
          <button onClick={loadPieces} className="text-xs font-medium text-red-600 hover:text-red-800 cursor-pointer">
            Retry
          </button>
        </div>
      )}

      <div className="bg-white border border-gray-200/60 rounded-2xl p-4 shadow-sm mb-4">
        <div className="flex flex-wrap gap-2 mb-3">
          {STATUS_TABS.map((tab) => (
            <button
              key={tab}
              onClick={() => setStatusFilter(tab)}
              className={`text-xs font-medium px-3 py-1.5 rounded-lg cursor-pointer transition-colors ${
                statusFilter === tab
                  ? 'bg-orange-500 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          {TYPE_OPTIONS.map((type) => (
            <button
              key={type}
              onClick={() => setTypeFilter(type)}
              className={`text-xs font-medium px-3 py-1.5 rounded-lg cursor-pointer transition-colors ${
                typeFilter === type
                  ? 'bg-gray-800 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {type}
            </button>
          ))}
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="bg-white border border-gray-200/60 rounded-2xl shadow-sm">
          <EmptyState
            icon={FileText}
            title="No content pieces"
            description="Content will appear here once the content factory generates pieces."
          />
        </div>
      ) : (
        <div className="grid gap-4">
          {filtered.map((piece) => (
            <ContentCard
              key={piece.id}
              piece={piece}
              onStatusChange={handleStatusChange}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}
    </div>
  );
}
