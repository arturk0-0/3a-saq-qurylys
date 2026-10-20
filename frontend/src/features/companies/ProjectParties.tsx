import { Link } from 'react-router-dom'
import type { Complex } from '@/lib/types'
import { CitationLink } from './CitationLink'
import './companies.css'

export function ProjectParties({ complex_ }: { complex_: Complex }) {
  return <section className="company-parties" aria-label="Участники проекта"><h3>Участники проекта</h3>
    <div className="company-party-grid">{([
      ['Юридический застройщик', complex_.developer, 'developer'],
      ['Уполномоченная компания', complex_.authorizedCompany, 'authorized_company'],
    ] as const).map(([label, party, role]) => {
      const source = complex_.partySnapshots?.find(p => p.role === role)?.source ?? complex_.participantSource
      return <article key={label}><h4>{label}</h4>{party ? <>
      <Link className="detail-link" to={'/companies/' + encodeURIComponent(party.id)}>{party.name} →</Link>
      <p>БИН {party.bin}</p>{source && <CitationLink source={source} />}
      {!source && <p className="form-hint">Из внутренней карточки ЖК</p>}
    </> : <p>Сведения пока не найдены</p>}</article>})}</div>
    {complex_.coordinateSource && <p className="form-hint">Положение объекта — точка из карточки источника, точность требует сверки. <CitationLink source={complex_.coordinateSource} /></p>}
    {complex_.coordinateStatus === 'outside_city' && <p className="inline-notice">Точка источника не соответствует городу и не используется на карте. Адрес сохранён; положение требует сверки.</p>}
  </section>
}
