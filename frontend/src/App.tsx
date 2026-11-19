import { useEffect, useState } from 'react'
import { api, type CreatedCampaign, type Option } from './api'
import { CampaignCreator } from './components/CampaignCreator'
import { OfferEditor } from './components/OfferEditor'

type Tab = 'create' | 'edit'

export default function App() {
  const [tab, setTab] = useState<Tab>('create')
  const [campaigns, setCampaigns] = useState<CreatedCampaign[]>([])
  const [editCampaign, setEditCampaign] = useState<Option | null>(null)

  useEffect(() => {
    api.createdCampaigns().then(setCampaigns).catch(() => {})
  }, [])

  const openEditor = (c: CreatedCampaign) => {
    setEditCampaign({ id: c.keitaro_campaign_id, name: c.name })
    setTab('edit')
  }

  return (
    <div className="page">
      <header>
        <h1>Keitaro Wrapper</h1>
        <nav className="tabs">
          <button className={tab === 'create' ? 'active' : ''} onClick={() => setTab('create')}>
            Создать кампанию
          </button>
          <button className={tab === 'edit' ? 'active' : ''} onClick={() => setTab('edit')}>
            Редактор офферов
          </button>
        </nav>
      </header>

      {tab === 'edit' ? (
        <OfferEditor campaign={editCampaign} onCampaignChange={setEditCampaign} />
      ) : (
        <>
          <CampaignCreator onCreated={(c) => setCampaigns((prev) => [c, ...prev])} />

          <section className="card">
            <h2>Созданные кампании</h2>
            {campaigns.length === 0 ? (
              <p className="muted">Пока пусто</p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Название</th>
                      <th>Гео</th>
                      <th>Оффер</th>
                      <th>Ссылка</th>
                      <th>Создана</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {campaigns.map((c) => (
                      <tr key={c.id}>
                        <td>{c.keitaro_campaign_id}</td>
                        <td>{c.name}</td>
                        <td>{c.geo.join(', ')}</td>
                        <td>#{c.offer_id}</td>
                        <td>
                          <a href={c.url} target="_blank" rel="noreferrer">
                            {c.url}
                          </a>
                        </td>
                        <td>{new Date(c.created_at).toLocaleString()}</td>
                        <td>
                          <button type="button" className="ghost" onClick={() => openEditor(c)}>
                            Офферы
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}
