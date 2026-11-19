import { useEffect, useState, type FormEvent } from 'react'
import { api, type CreatedCampaign, type Option } from '../api'
import { Autocomplete } from './Autocomplete'

interface Props {
  onCreated: (c: CreatedCampaign) => void
}

function SelectField({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: Option[]
  value: number | ''
  onChange: (v: number | '') => void
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : '')} required>
        <option value="">— выберите —</option>
        {options.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
      </select>
    </label>
  )
}

export function CampaignCreator({ onCreated }: Props) {
  const [domains, setDomains] = useState<Option[]>([])
  const [groups, setGroups] = useState<Option[]>([])
  const [sources, setSources] = useState<Option[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)

  const [name, setName] = useState('')
  const [geo, setGeo] = useState('')
  const [offer, setOffer] = useState<Option | null>(null)
  const [domainId, setDomainId] = useState<number | ''>('')
  const [groupId, setGroupId] = useState<number | ''>('')
  const [sourceId, setSourceId] = useState<number | ''>('')

  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [created, setCreated] = useState<CreatedCampaign | null>(null)

  useEffect(() => {
    Promise.all([api.domains(), api.groups(), api.trafficSources()])
      .then(([d, g, s]) => {
        setDomains(d)
        setGroups(g)
        setSources(s)
      })
      .catch((e: Error) => setLoadError(e.message))
  }, [])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!offer) {
      setError('Выберите оффер')
      return
    }
    setSubmitting(true)
    setError(null)
    setCreated(null)
    try {
      const c = await api.createCampaign({
        name,
        geo,
        offer_id: offer.id,
        domain_id: Number(domainId),
        group_id: Number(groupId),
        traffic_source_id: Number(sourceId),
      })
      setCreated(c)
      onCreated(c)
      setName('')
      setGeo('')
      setOffer(null)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="card">
      <h2>New campaign</h2>
      {loadError && <div className="alert error">Не удалось загрузить справочники Keitaro: {loadError}</div>}
      <form onSubmit={submit} className="form">
        <label className="field">
          <span>Name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="имя кампании" required />
        </label>
        <label className="field">
          <span>Geo</span>
          <input value={geo} onChange={(e) => setGeo(e.target.value)} placeholder="MX, AU, RO" required />
        </label>
        <div className="field">
          <span>Offer</span>
          <Autocomplete value={offer} onChange={setOffer} search={api.offers} />
        </div>
        <SelectField label="Домен" options={domains} value={domainId} onChange={setDomainId} />
        <SelectField label="Группа" options={groups} value={groupId} onChange={setGroupId} />
        <SelectField label="Источник" options={sources} value={sourceId} onChange={setSourceId} />

        <button type="submit" className="primary" disabled={submitting}>
          {submitting ? 'Создаём…' : 'Create'}
        </button>
      </form>

      {error && <div className="alert error">{error}</div>}
      {created && (
        <div className="alert ok">
          Кампания «{created.name}» создана (ID {created.keitaro_campaign_id}).{' '}
          <a href={created.url} target="_blank" rel="noreferrer">
            {created.url}
          </a>
        </div>
      )}
    </section>
  )
}
