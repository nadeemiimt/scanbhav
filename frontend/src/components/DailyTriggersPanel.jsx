export function DailyTriggersPanel({ triggers }) {
  if (!triggers?.length) return null
  return (
    <ul className="reason-list compact daily-triggers-list">
      {triggers.map(t => (
        <li key={`${t.kind}-${t.label}`}>
          <strong>{t.label}:</strong> {t.level}
        </li>
      ))}
    </ul>
  )
}

export function dailyTriggersHint(triggers) {
  if (!triggers?.length) return 'Pullback, recovery, and invalidation levels'
  return triggers.slice(0, 3).map(t => `${t.label} ${t.level}`).join(' · ')
}
