import type { FactorCode, VerificationStatus } from './types'
import { ApiError } from './http'

export const factorLabels: Record<FactorCode, string> = {
  R1: 'Отсутствие применимого правового основания',
  R2: 'Предложение внести платёж',
  R3: 'Реклама строящегося жилья',
  R4: 'Коллективная жалоба о привлечении средств',
  R5: 'Разница готовности от 20 п. п.',
  R6: 'Существенная остановка или задержка работ',
}
export const statusLabels: Record<VerificationStatus, string> = {
  unknown: 'Нет подтверждения', proposed: 'Гипотеза AI', confirmed: 'Подтверждено', rejected: 'Отклонено',
}
export const basisLabels = {
  guarantee: 'Гарантия', regional_permit: 'Разрешение МИО', other_applicable: 'Иное применимое основание', unknown: 'Не установлено',
}
export const stageLabels = { planning: 'Планирование', under_construction: 'Строится', commissioned: 'Введён в эксплуатацию' }
export const cities = ['Усть-Каменогорск', 'Риддер', 'Алтай', 'Серебрянск', 'Шемонаиха', 'Зайсан']
export function formatDate(value: string | null | undefined) {
  if (!value) return 'Не указано'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Некорректная дата'
  return new Intl.DateTimeFormat('ru-KZ', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Qyzylorda' }).format(date)
}
export function localDateTime(value: string | null | undefined) {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}
export function errorMessage(error: unknown) {
  if (error instanceof ApiError && error.requestId) return `${error.message} Код обращения: ${error.requestId}`
  return error instanceof Error ? error.message : 'Не удалось выполнить действие'
}
