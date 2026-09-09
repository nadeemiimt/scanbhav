import { useCallback, useState } from 'react'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'

/**
 * Themed confirm dialog — drop-in replacement for window.confirm().
 * @returns {{ confirm: (opts) => Promise<boolean>, dialog: React.ReactNode }}
 */
export function useConfirmDialog() {
  const [state, setState] = useState(null)

  const confirm = useCallback(({
    title = 'Confirm',
    message,
    confirmLabel = 'Confirm',
    cancelLabel = 'Cancel',
    variant = 'default',
  }) => new Promise(resolve => {
    setState({
      title,
      message,
      confirmLabel,
      cancelLabel,
      variant,
      resolve,
    })
  }), [])

  const close = useCallback((result) => {
    setState(prev => {
      prev?.resolve?.(result)
      return null
    })
  }, [])

  const dialog = state ? (
    <ConfirmDialog
      open
      title={state.title}
      message={state.message}
      confirmLabel={state.confirmLabel}
      cancelLabel={state.cancelLabel}
      variant={state.variant}
      onConfirm={() => close(true)}
      onCancel={() => close(false)}
    />
  ) : null

  return { confirm, dialog }
}

export default useConfirmDialog
