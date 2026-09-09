import { IndicatorsReferencePage } from './IndicatorsReferencePage'

export function MethodPage({ go }) {
  return <IndicatorsReferencePage onNavigate={id => go?.(id)} />
}

export default MethodPage
