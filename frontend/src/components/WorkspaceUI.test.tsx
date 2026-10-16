import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { ErrorState, FormField } from './WorkspaceUI'

it('retries a failed read inside a valid editor without submitting that editor', () => {
  const submit = vi.fn((event: React.FormEvent) => event.preventDefault())
  const retry = vi.fn()
  render(<form onSubmit={submit}><input name="notes" defaultValue="Введённое решение" required /><ErrorState message="Нет связи" retry={retry} /></form>)
  fireEvent.click(screen.getByRole('button', { name: 'Повторить' }))
  expect(retry).toHaveBeenCalledOnce()
  expect(submit).not.toHaveBeenCalled()
  expect(screen.getByRole('textbox')).toHaveValue('Введённое решение')
})

it('keeps the field label concise and exposes instructions as its description', () => {
  render(<FormField label="Дата фиксации" hint="Местное время компьютера."><input type="datetime-local" /></FormField>)
  const control = screen.getByLabelText('Дата фиксации')
  expect(control).toHaveAccessibleName('Дата фиксации')
  expect(control).toHaveAccessibleDescription('Местное время компьютера.')
})
