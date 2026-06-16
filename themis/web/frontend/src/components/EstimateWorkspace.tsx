import { useRef, useState } from 'react'
import Papa from 'papaparse'
import { estimate } from '../api'
import { DagBuilder } from './DagBuilder'
import { ResultView, type ResultPayload } from './ResultView'

interface Dataset {
  name: string
  rows: Record<string, unknown>[]
  columns: string[]
}

export function EstimateWorkspace() {
  const [data, setData] = useState<Dataset | null>(null)
  const [busy, setBusy] = useState(false)
  const [payload, setPayload] = useState<ResultPayload | null>(null)
  const [error, setError] = useState<string | null>(null)

  function onFile(file: File) {
    Papa.parse<Record<string, unknown>>(file, {
      header: true,
      dynamicTyping: true,
      skipEmptyLines: true,
      complete: (res) => {
        const rows = res.data
        const columns = res.meta.fields ?? []
        if (!rows.length || !columns.length) {
          setError('这个 CSV 看起来是空的或没有表头。')
          return
        }
        setData({ name: file.name, rows, columns })
        setError(null)
      },
      error: (err) => setError('CSV 解析失败：' + err.message),
    })
  }

  async function runEstimate(program: Record<string, unknown>) {
    if (!data) {
      setError('请先上传一个 CSV 数据文件。')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const env = await estimate(program, data.rows)
      const r = env.results?.[0]
      if (r) setPayload({ asked: `${data.name} · ${data.rows.length} 行`, result: r, program })
      else setError('估计没有返回结果。')
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (payload) return <ResultView payload={payload} onReset={() => setPayload(null)} resetLabel="← 回到画布与数据" />

  return (
    <DagBuilder
      submitLabel={data ? '用数据估计 →' : '先上传数据'}
      onSubmit={runEstimate}
      busy={busy}
      intro={
        <div className="build__intro">
          <h2 className="build__title">用数据估计因果效应</h2>
          <p className="build__lede">
            画出因果图、上传一份 CSV(<b>每一列是一个变量,列名要和图里的变量名一致</b>),Themis 会在数据上跑识别 + 估计——给出真实数值,或者诚实地告诉你为什么估不了(混杂没测全 / 数据没重叠 / 样本太小)。
          </p>
        </div>
      }
      banner={
        <>
          <UploadZone data={data} onFile={onFile} onClear={() => setData(null)} />
          {error ? <div className="errbox" role="alert"><p className="errbox__msg">{error}</p></div> : null}
        </>
      }
    />
  )
}

function UploadZone({ data, onFile, onClear }: { data: Dataset | null; onFile: (f: File) => void; onClear: () => void }) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [hover, setHover] = useState(false)

  if (data) {
    return (
      <div className="dataset">
        <div className="dataset__head">
          <span className="dataset__name">📄 {data.name}</span>
          <span className="dataset__meta">{data.rows.length} 行 · {data.columns.length} 列</span>
          <button className="linklike" onClick={onClear}>换一个</button>
        </div>
        <div className="dataset__cols">
          {data.columns.map((c) => (
            <span key={c} className="datacol mono">{c}</span>
          ))}
        </div>
        <p className="dataset__hint">把上面画布里的变量名改成与这些列名一致,再点「用数据估计」。</p>
      </div>
    )
  }

  return (
    <button
      className={`dropzone ${hover ? 'dropzone--hover' : ''}`}
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setHover(true) }}
      onDragLeave={() => setHover(false)}
      onDrop={(e) => {
        e.preventDefault()
        setHover(false)
        const f = e.dataTransfer.files?.[0]
        if (f) onFile(f)
      }}
    >
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 16V4M7 9l5-5 5 5M5 20h14" />
      </svg>
      <span className="dropzone__main">拖入 CSV,或点击选择</span>
      <span className="dropzone__sub">第一行是列名(变量名),其余每行是一条观测</span>
      <input ref={inputRef} type="file" accept=".csv,text/csv" hidden onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])} />
    </button>
  )
}
