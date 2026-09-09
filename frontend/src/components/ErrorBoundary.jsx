import { Component } from 'react'
import { logError } from '../lib/logger'

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    logError('React error boundary', error, info?.componentStack)
  }

  render() {
    const { error } = this.state
    if (error) {
      return (
        <section className="panel error-boundary">
          <h3>Something went wrong</h3>
          <p className="subtle">{error.message || 'Unexpected UI error'}</p>
          <button
            type="button"
            className="primary"
            onClick={() => this.setState({ error: null })}
          >
            Try again
          </button>
        </section>
      )
    }
    return this.props.children
  }
}
