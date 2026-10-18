import { Component, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'

// Keep navigation available when a route chunk fails (offline or an older tab
// after publication). A reload retries imports at the current URL, without
// replaying API writes or repeatedly rendering React.lazy's cached rejection.
export class RouteBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() { return { failed: true } }

  render() {
    if (this.state.failed) return <section role="alert" className="panel content-pad">
      <h1 className="text-xl font-semibold">Не удалось загрузить раздел</h1>
      <p className="my-4">Проверьте подключение и перезагрузите страницу. Другие разделы можно открыть через меню.</p>
      <Button onClick={() => window.location.reload()}>Перезагрузить страницу</Button>
    </section>
    return this.props.children
  }
}
