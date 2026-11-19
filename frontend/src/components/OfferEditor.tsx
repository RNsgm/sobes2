import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type Draft, type EditorItem, type EditorState, type OfferStreamInfo, type Option } from '../api'
import { Autocomplete } from './Autocomplete'

interface Props {
  campaign: Option | null
  onCampaignChange: (c: Option | null) => void
}

const sameDraft = (a: EditorItem[], b: EditorItem[]) =>
  a.length === b.length &&
  a.every(
    (x, i) =>
      x.offer_id === b[i].offer_id && x.share === b[i].share && x.pinned === b[i].pinned && x.removed === b[i].removed,
  )

export function OfferEditor({ campaign, onCampaignChange }: Props) {
  const [streams, setStreams] = useState<OfferStreamInfo[]>([])
  const [streamId, setStreamId] = useState<number | null>(null)

  const [base, setBase] = useState<EditorState | null>(null) // состояние в Keitaro
  const [draft, setDraft] = useState<Draft | null>(null) // черновик

  const [loading, setLoading] = useState(false)
  const [applying, setApplying] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const reqId = useRef(0)

  // кампания -> потоки с офферами
  useEffect(() => {
    setStreams([])
    setStreamId(null)
    setBase(null)
    setDraft(null)
    setError(null)
    setNotice(null)
    if (!campaign) return
    api
      .offerStreams(campaign.id)
      .then((s) => {
        setStreams(s)
        if (s.length > 0) setStreamId(s[0].id)
        else setError('В кампании нет потока с офферами')
      })
      .catch((e: Error) => setError(e.message))
  }, [campaign])

  const load = useCallback((id: number) => {
    setLoading(true)
    setError(null)
    api
      .editor(id)
      .then((st) => {
        setBase(st)
        setDraft({ items: st.items, total: st.total, errors: st.errors })
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (streamId) load(streamId)
  }, [streamId, load])

  // каждое изменение черновика -> пересчёт процентов на бэкенде
  const update = (items: EditorItem[]) => {
    if (!streamId) return
    setNotice(null)
    setDraft((d) => (d ? { ...d, items } : d))
    const id = ++reqId.current
    api
      .rebalance(streamId, items)
      .then((r) => {
        if (id === reqId.current) setDraft(r)
      })
      .catch((e: Error) => setError(e.message))
  }

  const items = draft?.items ?? []

  const addOffer = (o: Option | null) => {
    if (!o) return
    const existing = items.find((i) => i.offer_id === o.id)
    if (existing) {
      if (existing.removed) update(items.map((i) => (i.offer_id === o.id ? { ...i, removed: false } : i)))
      return
    }
    update([
      ...items,
      { offer_id: o.id, name: o.name, share: 0, pinned: false, removed: false, original_share: null, state: 'active' },
    ])
  }

  const remove = (it: EditorItem) => {
    // новый (ещё не применённый) оффер просто убираем из черновика
    if (it.original_share === null) update(items.filter((i) => i.offer_id !== it.offer_id))
    else update(items.map((i) => (i.offer_id === it.offer_id ? { ...i, removed: true, pinned: false } : i)))
  }

  const undoRemove = (it: EditorItem) =>
    update(items.map((i) => (i.offer_id === it.offer_id ? { ...i, removed: false } : i)))

  const togglePin = (it: EditorItem) =>
    update(items.map((i) => (i.offer_id === it.offer_id ? { ...i, pinned: !i.pinned } : i)))

  // ручная правка процента = пин на этом значении
  const setShare = (it: EditorItem, value: string) => {
    const n = Math.max(0, Math.min(100, Math.round(Number(value) || 0)))
    update(items.map((i) => (i.offer_id === it.offer_id ? { ...i, share: n, pinned: true } : i)))
  }

  const restore = (offerId: number, name: string) => addOffer({ id: offerId, name })

  const apply = async () => {
    if (!streamId || !draft) return
    setApplying(true)
    setError(null)
    try {
      const st = await api.apply(streamId, draft.items)
      setBase(st)
      setDraft({ items: st.items, total: st.total, errors: st.errors })
      setNotice('Изменения применены в Keitaro')
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setApplying(false)
    }
  }

  const cancel = () => {
    if (!base) return
    reqId.current++
    setDraft({ items: base.items, total: base.total, errors: base.errors })
    setNotice(null)
    setError(null)
  }

  const dirty = !!base && !!draft && !sameDraft(base.items, draft.items)
  const inDraft = new Set(items.filter((i) => !i.removed).map((i) => i.offer_id))
  const removedVisible = (base?.removed ?? []).filter((r) => !items.some((i) => i.offer_id === r.offer_id))

  return (
    <section className="card">
      <h2>Редактор офферов</h2>
      <div className="form">
        <div className="field">
          <span>Кампания</span>
          <Autocomplete value={campaign} onChange={onCampaignChange} search={api.campaigns} />
        </div>
        {streams.length > 1 && (
          <label className="field">
            <span>Поток</span>
            <select value={streamId ?? ''} onChange={(e) => setStreamId(Number(e.target.value))}>
              {streams.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.offers_count} офф.)
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {error && <div className="alert error">{error}</div>}
      {loading && <p className="muted">Загрузка…</p>}

      {draft && base && !loading && (
        <>
          <div className="table-wrap editor-table">
            <table>
              <thead>
                <tr>
                  <th>Оффер</th>
                  <th className="num">Было</th>
                  <th className="num">Станет</th>
                  <th className="center">Пин</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {items.map((it) => {
                  const changed = !it.removed && it.original_share !== it.share
                  return (
                    <tr key={it.offer_id} className={it.removed ? 'row-removed' : it.original_share === null ? 'row-new' : ''}>
                      <td className="offer-name">
                        <span className="muted">#{it.offer_id}</span> {it.name}
                        {it.removed && <span className="badge red">будет удалён</span>}
                        {it.original_share === null && <span className="badge green">новый</span>}
                        {it.state !== 'active' && <span className="badge">{it.state}</span>}
                      </td>
                      <td className="num muted">{it.original_share === null ? '—' : `${it.original_share}%`}</td>
                      <td className="num">
                        {it.removed ? (
                          <span className="muted">0%</span>
                        ) : (
                          <span className={`share ${changed ? 'changed' : ''}`}>
                            <input
                              type="number"
                              min={0}
                              max={100}
                              value={it.share}
                              onChange={(e) => setShare(it, e.target.value)}
                              title="Ручное значение автоматически пинится"
                            />
                            %
                          </span>
                        )}
                      </td>
                      <td className="center">
                        <button
                          type="button"
                          className={`pin ${it.pinned ? 'on' : ''}`}
                          disabled={it.removed}
                          onClick={() => togglePin(it)}
                          title={it.pinned ? 'Снять пин' : 'Закрепить процент'}
                          aria-pressed={it.pinned}
                        >
                          📌
                        </button>
                      </td>
                      <td className="actions">
                        {it.removed ? (
                          <button type="button" className="ghost" onClick={() => undoRemove(it)}>
                            Не удалять
                          </button>
                        ) : (
                          <button type="button" className="ghost danger" onClick={() => remove(it)}>
                            Удалить
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
              <tfoot>
                <tr>
                  <td>Итого</td>
                  <td className="num muted">{base.total}%</td>
                  <td className={`num ${draft.total === 100 ? '' : 'error-text'}`}>
                    <b>{draft.total}%</b>
                  </td>
                  <td colSpan={2} />
                </tr>
              </tfoot>
            </table>
          </div>

          <div className="add-offer">
            <Autocomplete
              value={null}
              onChange={addOffer}
              search={api.offers}
              exclude={[...inDraft]}
              placeholder="Добавить оффер: поиск по названию или ID"
              resetOnPick
            />
          </div>

          {draft.errors.length > 0 && (
            <div className="alert error">
              {draft.errors.map((e) => (
                <div key={e}>{e}</div>
              ))}
            </div>
          )}
          {notice && <div className="alert ok">{notice}</div>}

          <div className="buttons">
            <button type="button" className="primary" disabled={!dirty || draft.errors.length > 0 || applying} onClick={apply}>
              {applying ? 'Применяем…' : 'Применить'}
            </button>
            <button type="button" className="secondary" disabled={!dirty || applying} onClick={cancel}>
              Отменить
            </button>
          </div>

          {removedVisible.length > 0 && (
            <div className="removed">
              <h3>Удалённые офферы</h3>
              <table>
                <tbody>
                  {removedVisible.map((r) => (
                    <tr key={r.offer_id}>
                      <td className="offer-name">
                        <span className="muted">#{r.offer_id}</span> {r.offer_name}
                      </td>
                      <td className="num muted">был {r.share}%</td>
                      <td className="muted">{new Date(r.removed_at).toLocaleString()}</td>
                      <td className="actions">
                        <button type="button" className="ghost" onClick={() => restore(r.offer_id, r.offer_name)}>
                          Вернуть
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  )
}
