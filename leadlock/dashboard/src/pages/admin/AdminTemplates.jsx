import { useState, useEffect } from 'react';
import { FileText, Plus, Edit2, Trash2, Copy } from 'lucide-react';
import { api } from '../../api/client';

const STEP_TYPES = ['first_contact', 'followup', 'breakup', 'custom'];
const inputStyle = { background: 'var(--surface-2)', border: '1px solid var(--border)', color: 'var(--text-primary)' };

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
        <div className="w-6 h-6 border-2 border-t-transparent rounded-full animate-spin" style={{ borderColor: '#a855f7', borderTopColor: 'transparent' }} />
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <FileText className="w-5 h-5" style={{ color: '#a855f7' }} />
          <div>
            <h1 className="text-[20px] font-bold" style={{ color: 'var(--text-primary)' }}>Email Templates</h1>
            <p className="text-[13px]" style={{ color: 'var(--text-tertiary)' }}>{templates.length} templates</p>
          </div>
        </div>
        <button onClick={() => { setEditing(null); setShowEditor(!showEditor); }}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-[13px] font-medium text-white"
          style={{ background: '#a855f7' }}>
          <Plus className="w-3.5 h-3.5" /> New Template
        </button>
      </div>

      {/* Editor */}
      {showEditor && (
        <div className="rounded-xl p-5 mb-6" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
          <h2 className="text-[14px] font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>
            {editing ? 'Edit Template' : 'Create Template'}
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wider mb-1" style={{ color: 'var(--text-tertiary)' }}>Name</label>
              <input type="text" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
                className="w-full px-3 py-2 rounded-md text-[13px] outline-none" style={inputStyle} placeholder="HVAC Step 1" />
            </div>
            <div>
              <label className="block text-[11px] font-medium uppercase tracking-wider mb-1" style={{ color: 'var(--text-tertiary)' }}>Step Type</label>
              <select value={form.step_type} onChange={e => setForm({ ...form, step_type: e.target.value })}
                className="w-full px-3 py-2 rounded-md text-[13px] outline-none" style={inputStyle}>
                {STEP_TYPES.map(t => <option key={t} value={t}>{t.replace('_', ' ')}</option>)}
              </select>
            </div>
          </div>
          <div className="mb-4">
            <label className="block text-[11px] font-medium uppercase tracking-wider mb-1" style={{ color: 'var(--text-tertiary)' }}>Subject Template</label>
            <input type="text" value={form.subject_template} onChange={e => setForm({ ...form, subject_template: e.target.value })}
              className="w-full px-3 py-2 rounded-md text-[13px] outline-none" style={inputStyle}
              placeholder="Quick question about {{company_name}}" />
          </div>
          <div className="mb-4">
            <label className="block text-[11px] font-medium uppercase tracking-wider mb-1" style={{ color: 'var(--text-tertiary)' }}>Body Template</label>
            <textarea value={form.body_template} onChange={e => setForm({ ...form, body_template: e.target.value })}
              className="w-full px-3 py-2 rounded-md text-[13px] outline-none h-32 resize-none font-mono" style={inputStyle}
              placeholder="Hi {{prospect_name}},\n\nI noticed..." />
          </div>
          <div className="mb-4">
            <label className="block text-[11px] font-medium uppercase tracking-wider mb-1" style={{ color: 'var(--text-tertiary)' }}>AI Instructions (optional)</label>
            <textarea value={form.ai_instructions} onChange={e => setForm({ ...form, ai_instructions: e.target.value })}
              className="w-full px-3 py-2 rounded-md text-[13px] outline-none h-20 resize-none" style={inputStyle}
              placeholder="Focus on speed-to-lead pain point. Mention their Google rating." />
          </div>
          <div className="flex items-center gap-3 mb-4">
            <label className="flex items-center gap-2 cursor-pointer">
              <input type="checkbox" checked={form.is_ai_generated}
                onChange={e => setForm({ ...form, is_ai_generated: e.target.checked })}
                className="w-4 h-4 rounded" />
              <span className="text-[12px]" style={{ color: 'var(--text-secondary)' }}>AI-generated (uses template as guidance)</span>
            </label>
          </div>
          <div className="flex gap-2">
            <button onClick={handleSave} disabled={!form.name}
              className="px-4 py-2 rounded-lg text-[13px] font-medium text-white disabled:opacity-50"
              style={{ background: '#a855f7' }}>
              {editing ? 'Update' : 'Create'}
            </button>
            <button onClick={() => { setShowEditor(false); setEditing(null); }}
              className="px-4 py-2 rounded-lg text-[13px] font-medium"
              style={{ color: 'var(--text-tertiary)', background: 'var(--surface-2)', border: '1px solid var(--border)' }}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Templates list */}
      {templates.length === 0 ? (
        <div className="text-center py-16 rounded-xl" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
          <FileText className="w-10 h-10 mx-auto mb-3" style={{ color: 'var(--text-tertiary)' }} />
          <p className="text-[14px] font-medium" style={{ color: 'var(--text-secondary)' }}>No templates yet</p>
          <p className="text-[12px] mt-1" style={{ color: 'var(--text-tertiary)' }}>Create templates to customize your outreach emails.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {templates.map(t => (
            <div key={t.id} className="rounded-xl p-4" style={{ background: 'var(--surface-1)', border: '1px solid var(--border)' }}>
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-[14px] font-semibold" style={{ color: 'var(--text-primary)' }}>{t.name}</h3>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-medium capitalize"
                      style={{ background: 'rgba(124, 91, 240, 0.1)', color: '#a855f7' }}>
                      {t.step_type?.replace('_', ' ')}
                    </span>
                    {t.is_ai_generated && (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-medium"
                        style={{ background: 'rgba(96, 165, 250, 0.1)', color: '#60a5fa' }}>
                        AI
                      </span>
                    )}
                  </div>
                  {t.subject_template && (
                    <p className="text-[12px] mt-1 font-mono" style={{ color: 'var(--text-tertiary)' }}>
                      Subject: {t.subject_template}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-1">
                  <button onClick={() => handleEdit(t)}
                    className="p-2 rounded-lg transition-colors hover:opacity-80"
                    style={{ background: 'var(--surface-2)' }}>
                    <Edit2 className="w-3.5 h-3.5" style={{ color: 'var(--text-tertiary)' }} />
                  </button>
                  <button onClick={() => handleDelete(t.id)}
                    className="p-2 rounded-lg transition-colors hover:opacity-80"
                    style={{ background: 'var(--surface-2)' }}>
                    <Trash2 className="w-3.5 h-3.5" style={{ color: '#f87171' }} />
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
