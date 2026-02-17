import { useState, useEffect } from 'react';
import { FileText, Plus, Pencil, Trash2, Sparkles, X } from 'lucide-react';
import { api } from '../../api/client';
import PageHeader from '../../components/ui/PageHeader';
import Badge from '../../components/ui/Badge';
import EmptyState from '../../components/ui/EmptyState';

const STEP_TYPES = ['first_contact', 'followup', 'breakup', 'custom'];

const INITIAL_FORM = {
  name: '',
  step_type: 'first_contact',
  subject_template: '',
  body_template: '',
  ai_instructions: '',
  is_ai_generated: true,
};

function TemplateModal({ form, editing, onChange, onSave, onClose }) {
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-6 border-b border-gray-200/60">
          <h2 className="text-lg font-semibold text-gray-900">
            {editing ? 'Edit Template' : 'Create Template'}
          </h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors cursor-pointer"
          >
            <X className="w-4 h-4 text-gray-400" />
          </button>
        </div>

        <div className="p-6 space-y-5">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">
                Template Name
              </label>
              <input
                type="text"
                value={form.name}
                onChange={(e) => onChange({ ...form, name: e.target.value })}
                className="w-full px-3 py-2.5 bg-white border border-gray-200 rounded-xl text-sm text-gray-900 placeholder:text-gray-400 outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100 transition-shadow"
                placeholder="HVAC Step 1"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">
                Step Type
              </label>
              <select
                value={form.step_type}
                onChange={(e) => onChange({ ...form, step_type: e.target.value })}
                className="w-full px-3 py-2.5 bg-white border border-gray-200 rounded-xl text-sm text-gray-900 outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100 transition-shadow cursor-pointer"
              >
                {STEP_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t.replace(/_/g, ' ')}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">
              Subject Template
            </label>
            <input
              type="text"
              value={form.subject_template}
              onChange={(e) => onChange({ ...form, subject_template: e.target.value })}
              className="w-full px-3 py-2.5 bg-white border border-gray-200 rounded-xl text-sm text-gray-900 placeholder:text-gray-400 outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100 transition-shadow"
              placeholder="Quick question about {{company_name}}"
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">
              Body Template
            </label>
            <textarea
              value={form.body_template}
              onChange={(e) => onChange({ ...form, body_template: e.target.value })}
              className="w-full px-3 py-2.5 bg-white border border-gray-200 rounded-xl text-sm text-gray-900 placeholder:text-gray-400 outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100 transition-shadow h-32 resize-none font-mono"
              placeholder={'Hi {{prospect_name}},\n\nI noticed...'}
            />
          </div>

          <div>
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wider mb-1.5">
              AI Instructions (optional)
            </label>
            <textarea
              value={form.ai_instructions}
              onChange={(e) => onChange({ ...form, ai_instructions: e.target.value })}
              className="w-full px-3 py-2.5 bg-white border border-gray-200 rounded-xl text-sm text-gray-900 placeholder:text-gray-400 outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100 transition-shadow h-20 resize-none"
              placeholder="Focus on speed-to-lead pain point. Mention their Google rating."
            />
          </div>

          <label className="flex items-center gap-2.5 cursor-pointer">
            <input
              type="checkbox"
              checked={form.is_ai_generated}
              onChange={(e) => onChange({ ...form, is_ai_generated: e.target.checked })}
              className="w-4 h-4 rounded border-gray-300 text-orange-500 focus:ring-orange-500 cursor-pointer"
            />
            <span className="text-sm text-gray-700">
              AI-generated (uses template as guidance)
            </span>
          </label>
        </div>

        <div className="flex items-center justify-end gap-2 px-6 py-4 border-t border-gray-200/60">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-xl text-sm font-medium text-gray-500 bg-white border border-gray-200 hover:bg-gray-50 transition-colors cursor-pointer"
          >
            Cancel
          </button>
          <button
            onClick={onSave}
            disabled={!form.name}
            className="px-4 py-2 rounded-xl text-sm font-medium text-white bg-orange-500 hover:bg-orange-600 disabled:opacity-50 transition-colors cursor-pointer"
          >
            {editing ? 'Update' : 'Create'}
          </button>
        </div>
      </div>
    </div>
  );
}

function TemplateCard({ template, onEdit, onDelete }) {
  return (
    <div className="bg-white border border-gray-200/60 rounded-xl p-5 mb-3 hover:shadow-md transition-shadow">
      <div className="flex items-center justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-sm font-semibold text-gray-900 truncate">
              {template.name}
            </h3>
            <Badge variant="info">
              {template.step_type?.replace(/_/g, ' ')}
            </Badge>
            {template.is_ai_generated && (
              <Badge variant="info">
                <Sparkles className="w-3 h-3 mr-1" /> AI
              </Badge>
            )}
          </div>
          {template.subject_template && (
            <p className="text-sm text-gray-500 truncate font-mono">
              Subject: {template.subject_template}
            </p>
          )}
        </div>
        <div className="flex items-center gap-1.5 ml-4 shrink-0">
          <button
            onClick={() => onEdit(template)}
            className="p-2 rounded-xl bg-white border border-gray-200/60 hover:bg-gray-50 transition-colors cursor-pointer"
          >
            <Pencil className="w-3.5 h-3.5 text-gray-400" />
          </button>
          <button
            onClick={() => onDelete(template.id)}
            className="p-2 rounded-xl bg-white border border-gray-200/60 hover:bg-red-50 transition-colors cursor-pointer"
          >
            <Trash2 className="w-3.5 h-3.5 text-red-400" />
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AdminTemplates() {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showEditor, setShowEditor] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(INITIAL_FORM);

  useEffect(() => {
    loadTemplates();
  }, []);

  const loadTemplates = async () => {
    try {
      const data = await api.getTemplates();
      setTemplates(data.templates || []);
    } catch {
      // API not yet implemented
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    try {
      if (editing) {
        await api.updateTemplate(editing.id, form);
      } else {
        await api.createTemplate(form);
      }
      setShowEditor(false);
      setEditing(null);
      setForm(INITIAL_FORM);
      loadTemplates();
    } catch (err) {
      console.error('Failed to save template:', err);
    }
  };

  const handleEdit = (template) => {
    setEditing(template);
    setForm({
      name: template.name,
      step_type: template.step_type,
      subject_template: template.subject_template || '',
      body_template: template.body_template || '',
      ai_instructions: template.ai_instructions || '',
      is_ai_generated: template.is_ai_generated,
    });
    setShowEditor(true);
  };

  const handleDelete = async (id) => {
    try {
      await api.deleteTemplate(id);
      loadTemplates();
    } catch (err) {
      console.error('Failed to delete template:', err);
    }
  };

  const handleClose = () => {
    setShowEditor(false);
    setEditing(null);
    setForm(INITIAL_FORM);
  };

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
        title="Email Templates"
        subtitle={`${templates.length} template${templates.length !== 1 ? 's' : ''}`}
        actions={
          <button
            onClick={() => { setEditing(null); setForm(INITIAL_FORM); setShowEditor(true); }}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium text-white bg-orange-500 hover:bg-orange-600 transition-colors cursor-pointer"
          >
            <Plus className="w-4 h-4" /> New Template
          </button>
        }
      />

      {showEditor && (
        <TemplateModal
          form={form}
          editing={editing}
          onChange={setForm}
          onSave={handleSave}
          onClose={handleClose}
        />
      )}

      {templates.length === 0 ? (
        <div className="bg-white border border-gray-200/60 rounded-2xl shadow-sm">
          <EmptyState
            icon={FileText}
            title="No templates yet"
            description="Create templates to customize your outreach emails."
            action={
              <button
                onClick={() => setShowEditor(true)}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium text-white bg-orange-500 hover:bg-orange-600 transition-colors cursor-pointer"
              >
                <Plus className="w-4 h-4" /> Create Template
              </button>
            }
          />
        </div>
      ) : (
        <div>
          {templates.map((t) => (
            <TemplateCard
              key={t.id}
              template={t}
              onEdit={handleEdit}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}
    </div>
  );
}
