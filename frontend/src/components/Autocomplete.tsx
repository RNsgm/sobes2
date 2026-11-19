import { useEffect, useRef, useState } from 'react'
import type { Option } from '../api'

interface Props {
  value: Option | null
  onChange: (o: Option | null) => void
  search: (q: string) => Promise<Option[]>
  placeholder?: string
  /** id, которые не показывать в подсказках */
  exclude?: number[]
  /** режим «выбрал — и сразу очистил поле» (например, добавление оффера) */
  resetOnPick?: boolean
}

export function Autocomplete({ value, onChange, search, placeholder, exclude = [], resetOnPick }: Props) {
  const [query, setQuery] = useState('')
  const [items, setItems] = useState<Option[]>([])
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const boxRef = useRef<HTMLDivElement>(null)

  // поиск с debounce
  useEffect(() => {
    if (!open) return
    let cancelled = false
    const t = setTimeout(() => {
      search(query)
        .then((r) => {
          if (cancelled) return
          setItems(r)
          setActive(0)
          setError(null)
        })
        .catch((e: Error) => !cancelled && setError(e.message))
    }, 250)
    return () => {
      cancelled = true
      clearTimeout(t)
    }
  }, [query, open, search])

  // закрытие по клику снаружи
  useEffect(() => {
    const h = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])

  const visible = items.filter((o) => !exclude.includes(o.id))

  const pick = (o: Option) => {
    onChange(o)
    setQuery('')
    setOpen(false)
  }

  if (value && !resetOnPick) {
    return (
      <div className="chip">
        <span>
          <span className="muted">#{value.id}</span> {value.name}
        </span>
        <button type="button" className="link" onClick={() => onChange(null)} aria-label="Сбросить">
          ×
        </button>
      </div>
    )
  }

  return (
    <div className="ac" ref={boxRef}>
      <input
        placeholder={placeholder ?? 'Поиск по названию или ID'}
        value={query}
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          setQuery(e.target.value)
          setOpen(true)
        }}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') setActive((a) => Math.min(a + 1, visible.length - 1))
          else if (e.key === 'ArrowUp') setActive((a) => Math.max(a - 1, 0))
          else if (e.key === 'Enter' && open && visible[active]) {
            e.preventDefault()
            pick(visible[active])
          } else if (e.key === 'Escape') setOpen(false)
        }}
      />
      {open && (
        <ul className="ac-list">
          {error && <li className="ac-empty error">{error}</li>}
          {!error && visible.length === 0 && <li className="ac-empty">Ничего не найдено</li>}
          {visible.map((o, i) => (
            <li
              key={o.id}
              className={i === active ? 'active' : ''}
              onMouseEnter={() => setActive(i)}
              onMouseDown={(e) => {
                e.preventDefault()
                pick(o)
              }}
            >
              <span className="muted">#{o.id}</span> {o.name}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
