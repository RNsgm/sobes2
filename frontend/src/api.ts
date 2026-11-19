export interface Option {
  id: number
  name: string
}

export interface CampaignCreatePayload {
  name: string
  geo: string
  offer_id: number
  domain_id: number
  group_id: number
  traffic_source_id: number
}

export interface CreatedCampaign {
  id: number
  keitaro_campaign_id: number
  name: string
  alias: string
  url: string
  geo: string[]
  offer_id: number
  domain_id: number
  group_id: number
  traffic_source_id: number
  geo_stream_id: number
  offer_stream_id: number
  created_at: string
}

export interface OfferStreamInfo {
  id: number
  name: string
  offers_count: number
}

export interface EditorItem {
  offer_id: number
  name: string
  share: number
  pinned: boolean
  removed: boolean
  original_share: number | null
  state: string
}

export interface RemovedOffer {
  offer_id: number
  offer_name: string
  share: number
  removed_at: string
}

export interface Draft {
  items: EditorItem[]
  total: number
  errors: string[]
}

export interface EditorState extends Draft {
  campaign_id: number
  stream_id: number
  stream_name: string
  removed: RemovedOffer[]
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!resp.ok) {
    let detail = `${resp.status} ${resp.statusText}`
    try {
      const body = await resp.json()
      if (typeof body.detail === 'string') detail = body.detail
      else if (Array.isArray(body.detail))
        detail = body.detail.map((d: { msg: string }) => d.msg.replace(/^Value error, /, '')).join('; ')
    } catch {
      /* тело не JSON */
    }
    throw new Error(detail)
  }
  return resp.json() as Promise<T>
}

export const api = {
  domains: () => request<Option[]>('/domains'),
  groups: () => request<Option[]>('/groups'),
  trafficSources: () => request<Option[]>('/traffic-sources'),
  offers: (q: string) => request<Option[]>(`/offers?q=${encodeURIComponent(q)}&limit=20`),
  createCampaign: (data: CampaignCreatePayload) =>
    request<CreatedCampaign>('/campaigns', { method: 'POST', body: JSON.stringify(data) }),
  createdCampaigns: () => request<CreatedCampaign[]>('/campaigns/created'),
  campaigns: (q: string) => request<Option[]>(`/campaigns?q=${encodeURIComponent(q)}&limit=30`),
  offerStreams: (campaignId: number) => request<OfferStreamInfo[]>(`/campaigns/${campaignId}/offer-streams`),
  editor: (streamId: number, refresh = false) =>
    request<EditorState>(`/streams/${streamId}/editor${refresh ? '?refresh=true' : ''}`),
  rebalance: (streamId: number, items: EditorItem[]) =>
    request<Draft>(`/streams/${streamId}/rebalance`, { method: 'POST', body: JSON.stringify({ items }) }),
  apply: (streamId: number, items: EditorItem[]) =>
    request<EditorState>(`/streams/${streamId}/apply`, { method: 'POST', body: JSON.stringify({ items }) }),
}
