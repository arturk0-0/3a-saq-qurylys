import { Link } from 'react-router-dom'

const basisSources = [
  { name: 'Homeportal · КЖК', url: 'https://homeportal.kz', purpose: 'Сверка сведений о ЖК, гарантиях и разрешениях.' },
  { name: 'E-License', url: 'https://elicense.kz', purpose: 'Сверка конкретного разрешительного документа, его вида и статуса.' },
  { name: 'Qazreestr', url: 'https://qazreestr.kz', purpose: 'Сведения по долевому строительству; доступность конкретных записей проверяется отдельно.' },
  { name: 'Ashyq Data · объекты долевого строительства', url: 'https://ashyq.data.gov.kz/dataset/magda-ds-b80110e9-218a-42ba-b8c8-01fa5e4c82c8', purpose: 'Проверяйте состав набора, первичного поставщика, дату обновления и реквизиты записи.' },
]
const contextSources = [
  { name: 'eQurylys', url: 'https://reestr.equrylys.kz/organizations', purpose: 'Сведения о строительных организациях.' },
  { name: 'eGov', url: 'https://egov.kz', purpose: 'Услуги проверки юридических лиц; отдельные услуги могут требовать входа.' },
  { name: 'КГД', url: 'https://kgd.gov.kz', purpose: 'Налоговые сведения. Задолженность сама по себе не подтверждает R1–R6.' },
  { name: 'Реестр обязательных требований', url: 'https://rsp.gov.kz', purpose: 'Требования в сфере предпринимательства; не подтверждает регистрацию юридического лица.' },
  { name: 'Публичная кадастровая карта', url: 'https://map.gov4c.kz/egkn/', purpose: 'Сведения о земле и расположении; не заменяют проверку основания привлечения денег.' },
  { name: 'Открытые данные РК', url: 'https://data.egov.kz', purpose: 'Поиск наборов данных с проверкой поставщика, состава и актуальности.' },
  { name: 'Реестр недобросовестных участников госзакупок', url: 'https://procurement.gov.kz/ru/registry/rnu', purpose: 'Контекст участия в госзакупках; не является выводом о долевом строительстве.' },
]

function SourceList({ sources }: { sources: typeof basisSources }) {
  return <ul className="mt-3 space-y-3">{sources.map((source) => <li key={source.url}>
    <a className="detail-link" href={source.url} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">{source.name} ↗</a>
    <p className="form-hint">{source.purpose}</p>
  </li>)}</ul>
}

export function PublicSources({ complexId, demo }: { complexId: string; demo: boolean }) {
  return <section className="mt-6 border-t border-border pt-5" aria-label="Открытые источники для сверки">
    <h3 className="font-semibold">Открытые источники для ручной сверки</h3>
    <p className="form-hint">Ссылки открываются отдельно. Данные из реестров не загружаются автоматически; совпадение проверяет аналитик по БИН, адресу и очереди строительства.</p>
    {demo && <p className="inline-notice">Этот ЖК вымышленный. Записи о нём в реальных реестрах не ожидаются; отсутствие совпадения не подтверждает R1.</p>}
    <SourceList sources={basisSources} />
    <details className="mt-4"><summary className="cursor-pointer font-medium">Дополнительные источники об организации и объекте</summary><SourceList sources={contextSources} /></details>
    <p className="form-hint mt-4">Лицензия организации, права на землю и разрешение на привлечение денег — разные документы. Действующая применимая гарантия также может быть правовым основанием.</p>
    <Link className="detail-link mt-3" to={`/complexes/${encodeURIComponent(complexId)}?tab=evidence`}>Зафиксировать результат проверки →</Link>
  </section>
}
