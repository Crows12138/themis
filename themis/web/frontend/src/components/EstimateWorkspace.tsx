import { useRef, useState } from 'react'
import Papa from 'papaparse'
import { errorText, estimate } from '../api'
import { BIOMED_PROGRAM, biomedSampleRows, naiveDiff, queryXY, rowsToCsv } from '../lib/biomed'
import { fill, useLang, type Words } from '../lib/language'
import { DagBuilder } from './DagBuilder'
import { ResultView, type ResultPayload } from './ResultView'

const SAYS = {
  emptyCsv: { zh: '这个 CSV 看起来是空的或没有表头。', en: 'That CSV looks empty, or it has no header row.' },
  parseFailed: { zh: 'CSV 解析失败：{why}', en: 'The CSV could not be parsed: {why}' },
  needData: { zh: '请先上传一个 CSV 数据文件。', en: 'Upload a CSV first.' },
  noResult: { zh: '估计没有返回结果。', en: 'The estimate came back with nothing.' },
  asked: { zh: '{name} · {n} 行', en: '{name} · {n} rows' },
  builtinAsked: {
    zh: '内置示例 · 靶向药 → 肿瘤反应（疾病严重程度是混杂）',
    en: 'Built-in example · targeted drug → tumour response (disease severity confounds it)',
  },
  back: { zh: '← 回到画布与数据', en: '← Back to the canvas and the data' },
  estimateGo: { zh: '用数据估计 →', en: 'Estimate from the data →' },
  needUpload: { zh: '先上传数据', en: 'Upload data first' },
  title: { zh: '用数据估计因果效应', en: 'Estimate a causal effect from data' },
  ledeHead: { zh: '画出因果图、上传一份 CSV（', en: 'Draw the causal graph and upload a CSV (' },
  ledeLead: { zh: '每一列是一个变量，列名要和图里的变量名一致', en: 'one column per variable, column names matching the names in the graph' },
  ledeTail: {
    zh: '），Themis 会在数据上跑识别 + 估计——给出真实数值，或者诚实地告诉你为什么估不了（混杂没测全 / 数据没重叠 / 样本太小）。',
    en: '). Themis runs identification and estimation on it, and either gives you a real number or says honestly why it cannot — unmeasured confounding, no overlap, too small a sample.',
  },
  running: { zh: '运行中…', en: 'Running…' },
  demo: { zh: '▶ 一键看核心对比：靶向药 + 混杂（内置示例）', en: '▶ See the core comparison: a targeted drug with confounding (built-in example)' },
  noDataYet: { zh: '没有数据？', en: 'No data?' },
  downloadSample: { zh: '下载示例 CSV（靶向药+混杂）', en: 'Download the sample CSV (drug + confounder)' },
  tryUpload: { zh: '试试上传流程。', en: 'and try the upload.' },
  rowsCols: { zh: '{rows} 行 · {cols} 列', en: '{rows} rows · {cols} columns' },
  swap: { zh: '换一个', en: 'Use another' },
  matchNames: {
    zh: '把上面画布里的变量名改成与这些列名一致，再点「用数据估计」。',
    en: 'Rename the variables on the canvas above to match these columns, then estimate.',
  },
  drop: { zh: '拖入 CSV，或点击选择', en: 'Drop a CSV here, or click to choose one' },
  dropSub: { zh: '第一行是列名（变量名），其余每行是一条观测', en: 'The first row is the column names; every other row is one observation' },
} satisfies Record<string, Words>

interface Dataset {
  name: string
  rows: Record<string, unknown>[]
  columns: string[]
}

export function EstimateWorkspace({
  initialProgram,
  onSendTo,
}: {
  initialProgram?: Record<string, unknown>
  onSendTo?: (target: 'ask' | 'build' | 'estimate', program: Record<string, unknown>) => void
} = {}) {
  const [data, setData] = useState<Dataset | null>(null)
  const [busy, setBusy] = useState(false)
  const [payload, setPayload] = useState<ResultPayload | null>(null)
  const [error, setError] = useState<string | null>(null)
  const lang = useLang()

  function onFile(file: File) {
    Papa.parse<Record<string, unknown>>(file, {
      header: true,
      dynamicTyping: true,
      skipEmptyLines: true,
      complete: (res) => {
        const rows = res.data
        const columns = res.meta.fields ?? []
        if (!rows.length || !columns.length) {
          setError(fill(SAYS.emptyCsv, lang))
          return
        }
        setData({ name: file.name, rows, columns })
        setError(null)
      },
      error: (err) => setError(fill(SAYS.parseFailed, lang, { why: err.message })),
    })
  }

  async function runEstimate(program: Record<string, unknown>) {
    if (!data) {
      setError(fill(SAYS.needData, lang))
      return
    }
    setBusy(true)
    setError(null)
    try {
      const env = await estimate(program, data.rows)
      const r = env.results?.[0]
      const { x, y } = queryXY(program)
      const naive = x && y ? naiveDiff(data.rows, x, y) : null
      if (r) setPayload({ asked: fill(SAYS.asked, lang, { name: data.name, n: data.rows.length }), result: r, program, naive })
      else setError(fill(SAYS.noResult, lang))
    } catch (e) {
      setError(errorText(e, lang))
    } finally {
      setBusy(false)
    }
  }

  async function runBuiltin() {
    setBusy(true)
    setError(null)
    try {
      const rows = biomedSampleRows()
      const naive = naiveDiff(rows, 'targeted_drug', 'tumor_response')
      const env = await estimate(BIOMED_PROGRAM, rows)
      const r = env.results?.[0]
      if (r) setPayload({ asked: fill(SAYS.builtinAsked, lang), result: r, program: BIOMED_PROGRAM, naive })
      else setError(fill(SAYS.noResult, lang))
    } catch (e) {
      setError(errorText(e, lang))
    } finally {
      setBusy(false)
    }
  }

  function downloadSample() {
    const csv = rowsToCsv(biomedSampleRows())
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
    const a = document.createElement('a')
    a.href = url
    a.download = 'themis_biomed_sample.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  if (payload) return <ResultView payload={payload} onSendTo={onSendTo} onReset={() => setPayload(null)} resetLabel={fill(SAYS.back, lang)} />

  return (
    <DagBuilder
      submitLabel={fill(data ? SAYS.estimateGo : SAYS.needUpload, lang)}
      onSubmit={runEstimate}
      busy={busy}
      initialProgram={initialProgram}
      intro={
        <div className="build__intro">
          <h2 className="build__title">{fill(SAYS.title, lang)}</h2>
          <p className="build__lede">
            {fill(SAYS.ledeHead, lang)}
            <b>{fill(SAYS.ledeLead, lang)}</b>
            {fill(SAYS.ledeTail, lang)}
          </p>
          <button className="btn demo__go" onClick={runBuiltin} disabled={busy}>
            {fill(busy ? SAYS.running : SAYS.demo, lang)}
          </button>
        </div>
      }
      banner={
        <>
          <UploadZone data={data} onFile={onFile} onClear={() => setData(null)} />
          {!data ? (
            <p className="upload__sample">
              {fill(SAYS.noDataYet, lang)}{' '}
              <button className="linklike" onClick={downloadSample}>{fill(SAYS.downloadSample, lang)}</button>{' '}
              {fill(SAYS.tryUpload, lang)}
            </p>
          ) : null}
          {error ? <div className="errbox" role="alert"><p className="errbox__msg">{error}</p></div> : null}
        </>
      }
    />
  )
}

function UploadZone({ data, onFile, onClear }: { data: Dataset | null; onFile: (f: File) => void; onClear: () => void }) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [hover, setHover] = useState(false)
  const lang = useLang()

  if (data) {
    return (
      <div className="dataset">
        <div className="dataset__head">
          <span className="dataset__name">📄 {data.name}</span>
          <span className="dataset__meta">{fill(SAYS.rowsCols, lang, { rows: data.rows.length, cols: data.columns.length })}</span>
          <button className="linklike" onClick={onClear}>{fill(SAYS.swap, lang)}</button>
        </div>
        <div className="dataset__cols">
          {data.columns.map((c) => (
            <span key={c} className="datacol mono">{c}</span>
          ))}
        </div>
        <p className="dataset__hint">{fill(SAYS.matchNames, lang)}</p>
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
      <span className="dropzone__main">{fill(SAYS.drop, lang)}</span>
      <span className="dropzone__sub">{fill(SAYS.dropSub, lang)}</span>
      <input ref={inputRef} type="file" accept=".csv,text/csv" hidden onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0])} />
    </button>
  )
}
