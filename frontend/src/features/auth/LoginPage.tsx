import { useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { useAuth } from './AuthProvider'

export function LoginPage() {
  const { signIn } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try { await signIn(email.trim(), password) }
    catch (error) { setError(error instanceof Error ? error.message : 'Не удалось войти') }
    finally { setPassword(''); setBusy(false) }
  }

  return <section className="mx-auto max-w-md rounded-xl border border-border bg-background p-8">
    <p className="text-sm font-medium text-primary">Рабочее пространство аналитика · ВКО</p>
    <h1 className="mt-2 text-3xl font-semibold">Вход в SAQ QURYLYS</h1>
    <p className="mt-3 text-sm text-muted-foreground">Используйте учётную запись, выданную администратором.</p>
    <form onSubmit={submit} className="mt-6 space-y-4">
      <label className="block text-sm font-medium">Электронная почта
        <input required type="email" autoComplete="username" value={email}
          onChange={(event) => setEmail(event.target.value)} className="mt-2 w-full rounded-md border border-border p-3" />
      </label>
      <label className="block text-sm font-medium">Пароль
        <input required type="password" autoComplete="current-password" value={password}
          onChange={(event) => setPassword(event.target.value)} className="mt-2 w-full rounded-md border border-border p-3" />
      </label>
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      <Button disabled={busy} type="submit" className="w-full">{busy ? 'Входим…' : 'Войти'}</Button>
    </form>
    <p className="mt-6 text-xs text-muted-foreground">Система помогает проверять потенциальные риски.
      Итоговое решение всегда принимает аналитик.</p>
  </section>
}
