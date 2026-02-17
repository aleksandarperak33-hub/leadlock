import { useState, useEffect } from 'react';
import { FileText, Plus, Edit2, Trash2 } from 'lucide-react';
import { api } from '../../api/client';

const STEP_TYPES = ['first_contact', 'followup', 'breakup', 'custom'];

export default function AdminTemplates() {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showEditor, setShowEditor] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({
    name: '', step_type: 'first_contact',
    subject_template: '', body_template: '',
    ai_instructions: '', is_ai_generated: true,
  });

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
      setForm({ name: '', step_type: 'first_contact', subject_template: '', body_template: '', ai_instructions: '', is_ai_generated: true });
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

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 border-2 border-orange-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-orange-50">
            <FileText className="w-4.5 h-4.5 text-orange-600" />
          </div>
          <div>
            <h1 className="text-xl font-semibold text-gray-900">Email Templates</h1>
            <p className="text-sm text-gray-500">{templates.length} templates</p>
          </div>
        </div>
        <button
          onClick={() => { setEditing(null); setShowEditor(!showEditor); }}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium text-white bg-orange-600 hover:bg-orange-700 transition-colors cursor-pointer"
        >
          <Plus className="w-4 h-4" /> New Template
        </button>
      </div>

      {/* Editor */}
      {showEditor && (
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5 mb-6">
          <h2 className="text-sm font-semibold text-gray-900 mb-4">
            {editing ? 'Edit Template' : 'Create Template'}
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block text-xs font-medium uppercase tracking-wider text-gray-400 mb-1.5">Name</label>
              <input
                type="text"
                value={form.name}
                onChange={e => setForm({ ...form, name: e.target.value })}
                className="w-full px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm text-gray-900 placeholder:text-gray-400 outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100 transition-shadow"
                placeholder="HVAC Step 1"
              />
            </div>
            <div>
              <label className="block text-xs font-medium uppercase tracking-wider text-gray-400 mb-1.5">Step Type</label>
              <select
                value={form.step_type}
                onChange={e => setForm({ ...form, step_type: e.target.value })}
                className="w-full px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm text-gray-900 outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100 transition-shadow cursor-pointer"
              >
                {STEP_TYPES.map(t => <option key={t} value={t}>{t.replace('_', ' ')}</option>)}
              </select>
            </div>
          </div>
          <div className="mb-4">
            <label className="block text-xs font-medium uppercase tracking-wider text-gray-400 mb-1.5">Subject Template</label>
            <input
              type="text"
              value={form.subject_template}
              onChange={e => setForm({ ...form, subject_template: e.target.value })}
              className="w-full px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm text-gray-900 placeholder:text-gray-400 outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100 transition-shadow"
              placeholder="Quick question about {{company_name}}"
            />
          </div>
          <div className="mb-4">
            <label className="block text-xs font-medium uppercase tracking-wider text-gray-400 mb-1.5">Body Template</label>
            <textarea
              value={form.body_template}
              onChange={e => setForm({ ...form, body_template: e.target.value })}
              className="w-full px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm text-gray-900 placeholder:text-gray-400 outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100 transition-shadow h-32 resize-none font-mono"
              placeholder="Hi {{prospect_name}},&#10;&#10;I noticed..."
            />
          </div>
          <div className="mb-4">
            <label className="block text-xs font-medium uppercase tracking-wider text-gray-400 mb-1.5">AI Instructions (optional)</label>
            <textarea
              value={form.ai_instructions}
              onChange={e => setForm({ ...form, ai_instructions: e.target.value })}
              className="w-full px-3 py-2 bg-white border border-gray-200 rounded-lg text-sm text-gray-900 placeholder:text-gray-400 outline-none focus:border-orange-500 focus:ring-2 focus:ring-orange-100 transition-shadow h-20 resize-none"
              placeholder="Focus on speed-to-lead pain point. Mention their Google rating."
            />
          </div>
          <div className="flex items-center gap-3 mb-4">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={form.is_ai_generated}
                onChange={e => setForm({ ...form, is_ai_generated: e.target.checked })}
                className="w-4 h-4 rounded border-gray-300 text-orange-600 focus:ring-orange-500 cursor-pointer"
              />
              <span className="text-xs text-gray-700">AI-generated (uses template as guidance)</span>
            </label>
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleSave}
              disabled={!form.name}
              className="px-4 py-2 rounded-lg text-sm font-medium text-white bg-orange-600 hover:bg-orange-700 disabled:opacity-50 transition-colors cursor-pointer"
            >
              {editing ? 'Update' : 'Create'}
            </button>
            <button
              onClick={() => { setShowEditor(false); setEditing(null); }}
              className="px-4 py-2 rounded-lg text-sm font-medium text-gray-500 bg-white border border-gray-200 hover:bg-gray-50 transition-colors cursor-pointer"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Templates list */}
      {templates.length === 0 ? (
        <div className="bg-white border border-gray-200 rounded-xl shadow-sm text-center py-16">
          <FileText className="w-10 h-10 mx-auto mb-3 text-gray-300" />
          <p className="text-sm font-medium text-gray-700">No templates yet</p>
          <p className="text-xs text-gray-400 mt-1">Create templates to customize your outreach emails.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {templates.map(t => (
            <div key={t.id} className="bg-white border border-gray-200 rounded-xl shadow-sm p-4 hover:shadow-md transition-shadow">
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-semibold text-gray-900">{t.name}</h3>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-medium capitalize bg-orange-50 text-orange-700 border border-orange-100">
                      {t.step_type?.replace('_', ' ')}
                    </span>
                    {t.is_ai_generated && (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-blue-50 text-blue-700 border border-blue-100">
                        AI
                      </span>
                    )}
                  </div>
                  {t.subject_template && (
                    <p className="text-xs mt-1 font-mono text-gray-400">
                      Subject: {t.subject_template}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => handleEdit(t)}
                    className="p-2 rounded-lg bg-white border border-gray-200 hover:bg-gray-50 transition-colors cursor-pointer"
                  >
                    <Edit2 className="w-3.5 h-3.5 text-gray-400" />
                  </button>
                  <button
                    onClick={() => handleDelete(t.id)}
                    className="p-2 rounded-lg bg-white border border-gray-200 hover:bg-red-50 transition-colors cursor-pointer"
                  >
                    <Trash2 className="w-3.5 h-3.5 text-red-400" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
