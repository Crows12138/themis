// A result saved to a file the reader keeps, and opened again later.
//
// What the result view shows lives only in the page. The server keeps no
// answer, so a reload or a closed tab loses it, and a model's reply cannot
// be had again for the same words. The file holds what the view shows — the
// question as asked, the program, the kernel's result, the reply, the
// correction it came from — and the workspace it was made in, so that
// opening it puts it back where it was, with the same things offered.
//
// It is a record of a moment, not a live answer. Opened again it says when
// it was saved; anything re-run from it is run by the kernel of that day.

import { KernelError } from '../api'
import type { Revision } from '../components/Correction'
import type { ResultPayload, Workspace } from '../components/ResultView'
import type { QueryResult } from '../types'
import type { Words } from './language'

const SAYS = {
  notJson: { zh: '这个文件读不出来：它不是 JSON。', en: 'This file cannot be read: it is not JSON.' },
  notSaved: { zh: '这不是 Themis 保存的结果文件。', en: 'This is not a result saved by Themis.' },
  newer: {
    zh: '这个文件是更新版本的 Themis 保存的，这个版本读不了。',
    en: 'This file was saved by a newer Themis than this one, which cannot read it.',
  },
} satisfies Record<string, Words>

// The file says what it is, so that opening some other JSON is refused
// rather than drawn as a result out of whatever it holds.
const KIND = 'themis.saved_result'
// Raised when the shape changes in a way an older page cannot read.
const VERSION = 1
const WORKSPACES: readonly Workspace[] = ['ask', 'build', 'estimate']

interface SavedResult {
  kind: typeof KIND
  version: number
  // ISO 8601, UTC.
  saved_at: string
  workspace: Workspace
  asked: string
  result: QueryResult
  program?: Record<string, unknown>
  reply?: string
  naive?: number | null
  revision?: Revision
}

function stamp(at: Date): string {
  const two = (n: number) => String(n).padStart(2, '0')
  return `${at.getFullYear()}-${two(at.getMonth() + 1)}-${two(at.getDate())} ${two(at.getHours())}:${two(at.getMinutes())}`
}

// When a saved result was saved, in the reader's own clock. Digits only, so
// it reads the same in every language.
export function whenSaved(iso: string): string {
  const at = new Date(iso)
  return Number.isNaN(at.getTime()) ? iso : stamp(at)
}

export function saveResult(workspace: Workspace, shown: Omit<ResultPayload, 'savedAt'>): void {
  const now = new Date()
  const file: SavedResult = {
    kind: KIND,
    version: VERSION,
    saved_at: now.toISOString(),
    workspace,
    asked: shown.asked,
    result: shown.result,
    program: shown.program,
    reply: shown.reply,
    naive: shown.naive,
    revision: shown.revision,
  }
  const url = URL.createObjectURL(new Blob([JSON.stringify(file, null, 2)], { type: 'application/json' }))
  const a = document.createElement('a')
  a.href = url
  a.download = `themis-result-${stamp(now).replace(/[-: ]/g, '')}.json`
  a.click()
  URL.revokeObjectURL(url)
}

const isObject = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)

// What the result view reads without checking first. A file edited by hand
// can still hold something else deeper down; this is the shape, not a proof.
function isResult(v: unknown): v is QueryResult {
  return isObject(v) && typeof v.status === 'string' && typeof v.query_kind === 'string'
}

function isRevision(v: unknown): v is Revision {
  return isObject(v) && typeof v.said === 'string' && isObject(v.before) && isObject(v.after)
}

export async function openSaved(file: File): Promise<{ workspace: Workspace; payload: ResultPayload }> {
  let d: unknown
  try {
    d = JSON.parse(await file.text())
  } catch {
    throw new KernelError('', { words: SAYS.notJson })
  }
  if (!isObject(d) || d.kind !== KIND) throw new KernelError('', { words: SAYS.notSaved })
  if (typeof d.version !== 'number' || d.version > VERSION) throw new KernelError('', { words: SAYS.newer })
  const workspace = WORKSPACES.find((w) => w === d.workspace)
  if (
    !workspace ||
    typeof d.saved_at !== 'string' ||
    typeof d.asked !== 'string' ||
    !isResult(d.result) ||
    (d.program !== undefined && !isObject(d.program)) ||
    (d.reply !== undefined && typeof d.reply !== 'string') ||
    (d.naive !== undefined && d.naive !== null && typeof d.naive !== 'number') ||
    (d.revision !== undefined && !isRevision(d.revision))
  )
    throw new KernelError('', { words: SAYS.notSaved })
  return {
    workspace,
    payload: {
      asked: d.asked,
      result: d.result,
      program: d.program as Record<string, unknown> | undefined,
      reply: d.reply as string | undefined,
      naive: d.naive as number | null | undefined,
      revision: d.revision as Revision | undefined,
      savedAt: d.saved_at,
    },
  }
}
