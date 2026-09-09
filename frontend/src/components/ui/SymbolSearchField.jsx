export function SymbolSearchField({
  value,
  onChange,
  onPick,
  searching,
  suggestions,
  placeholder,
  inputId,
}) {
  return (
    <div className="search-box swing-search-box">
      <input
        id={inputId}
        value={value}
        onChange={e => onChange(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Enter' && onPick) {
            e.preventDefault()
            onPick()
          }
        }}
        placeholder={placeholder}
        autoComplete="off"
        aria-autocomplete="list"
        aria-expanded={suggestions.length > 0}
      />
      {searching && <p className="search-hint">Searching…</p>}
      {suggestions.length > 0 && (
        <div className="suggestions" role="listbox">
          {suggestions.map(item => (
            <button
              key={`${item.symbol}-${item.exchange}`}
              type="button"
              role="option"
              onMouseDown={e => e.preventDefault()}
              onClick={() => onPick(item.symbol)}
            >
              <b>{item.symbol}</b>
              <span>{item.name} {item.exchange && `· ${item.exchange}`}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
