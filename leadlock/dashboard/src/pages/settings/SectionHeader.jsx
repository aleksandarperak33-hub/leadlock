export function SectionHeader({ title, description }) {
  return (
    <div className="mb-6">
      <h2 className="text-lg font-semibold text-gray-900 mb-1">{title}</h2>
      {description && (
        <p className="text-sm text-gray-500">{description}</p>
      )}
    </div>
  );
}

export function SectionDivider() {
  return <div className="border-b border-gray-200/60 pb-8 mb-8" />;
}
