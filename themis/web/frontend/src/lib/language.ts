import { useSyncExternalStore } from 'react'

// Which language this surface is answering the reader in.
//
// The browser's half of `themis/language.py`, mirroring its two sets and its
// one lookup. A test pins both sets equal to the kernel's — a language the
// kernel gains and the browser does not is a page that cannot show what the
// answer has, and one the browser gains alone is a page offering a choice
// with nothing behind it.

// Answered in. What a chooser may offer, and what the kernel's `Lang` holds.
export const LANGS = ['zh', 'en'] as const

// Being written, and not yet offered. Words keyed by one of these are legal
// and are held to the same completeness as any other — what is not yet true
// of them is that every surface has been reached, and a page that offered a
// half-reached language would hand a reader half of another one.
// Empty, and an empty set is a claim: every language this build declares,
// it answers in. It stays because the third language will need it.
export const ARRIVING = [] as const

export type Lang = (typeof LANGS)[number] | (typeof ARRIVING)[number]

// Every language some text here is written in: the denominator of the
// completeness check, which is a wider question than what may be offered.
export const WRITTEN: readonly Lang[] = [...LANGS, ...ARRIVING]

// What a reader gets who has not chosen. The same default the kernel has,
// and for the same reason: it is the language every word here was written
// in first.
export const DEFAULT_LANG: Lang = 'zh'

// Where a reader's choice is kept between visits.
//
// The choice belongs to the reader, not to the page. A language picked once
// and forgotten on reload is a chooser that has to be used every time, which
// is close enough to not having been offered.
const KEPT = 'themis.lang'

// A tag this page may answer in, or null.
//
// Against `LANGS` and never against `WRITTEN`: the wider set is the
// denominator of the completeness check — being written in is what ARRIVING
// means — so nothing that reaches a reader may be validated against it.
// Everything arriving here was written by somebody who is not this build: a
// choice stored by a version that offered more languages, a browser asking
// for one nobody here writes. None of them is evidence that this build can
// answer.
function offered(tag: string | null | undefined): Lang | null {
  return (LANGS as readonly string[]).includes(tag ?? '')
    ? (tag as Lang)
    : null
}

// What the reader's browser itself asks for, in the order it asks.
//
// A region is not a language this build distinguishes, so `en-GB` is `en`.
// This is a preference and not a choice: a reader who says nothing has still
// told their browser something, and answering in a language they can read
// beats answering in the one this package happened to be written in first.
function requested(): Lang | null {
  if (typeof navigator === 'undefined') return null
  for (const tag of navigator.languages ?? [navigator.language]) {
    const lang = offered(tag?.split('-')[0])
    if (lang) return lang
  }
  return null
}

// Storage can be refused outright — private browsing, a third-party frame, a
// user who turned it off. A reader who cannot be remembered can still choose;
// nothing else here depends on it, so the refusal is not the reader's problem
// and is not reported to them.
function remembered(): Lang | null {
  try {
    return offered(localStorage.getItem(KEPT))
  } catch {
    return null
  }
}

let chosen: Lang = remembered() ?? requested() ?? DEFAULT_LANG
const listeners = new Set<() => void>()

// The page's own `lang` attribute, which is not decoration: it is what a
// screen reader picks a voice from, and what the browser hyphenates and
// matches fonts by. It is a second record of the one choice, so it is written
// where the choice is rather than by whoever happens to render.
function announce(): void {
  if (typeof document !== 'undefined') document.documentElement.lang = chosen
}

announce()

// The reader chose. Everything asking `useLang` re-renders.
export function chooseLang(lang: Lang): void {
  if (lang === chosen) return
  chosen = lang
  try {
    localStorage.setItem(KEPT, lang)
  } catch {
    // See `remembered`.
  }
  announce()
  for (const listener of listeners) listener()
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

// Which language THIS reader is reading in.
//
// A component asks; it does not import the answer. The difference mattered
// only once there was a choice to make, which is exactly why the question was
// named before then — and what it bought is that making the choice real
// changed this function and nothing else. Had every component imported
// `DEFAULT_LANG`, the switch would have been an edit in each of seventeen of
// them, and the pressure at that moment is to thread a prop through the ones
// that render nothing.
//
// So: components ask here, and pure modules take `lang` as a parameter. That
// is the whole boundary — `verdict.ts` is not a component and its functions
// keep their argument, filled in by whoever called them from a component.
export function useLang(): Lang {
  return useSyncExternalStore(subscribe, () => chosen)
}

// One thing's reader-facing text, by language. Generic because what a table
// holds per member is not always one string — a refusal is three sentences
// and a tier is a label with a gloss — and the language axis belongs around
// the whole of the text either way.
//
// Around the TEXT and nothing else: a fact that is the same in every
// language stays outside, or it becomes a second record of itself, free to
// say one thing to one reader and another to the next.
//
// Partial because a hole is a thing that can happen to a build, and `say` is
// where it is answered.
export type Words<T = string> = Partial<Record<Lang, T>>

// One thing's text in the reader's language, or `unknown`.
//
// Nothing falls back to another language. A page half in a language the
// reader did not ask for is the defect, not the fix — so a missing text
// reads as the identifier, which a reader can at least look up.
export function say<T>(words: Words<T> | undefined, lang: Lang, unknown: T): T {
  const said = words?.[lang]
  return said === undefined ? unknown : said
}

// One thing's sentence in the reader's language, with its holes filled.
//
// What `say` is for a word, this is for a sentence — and a sentence is where
// a second language stops being a lookup: the two put the same facts in
// different places, so the text cannot be a template literal. A template
// literal interpolates where it is written, which makes it a value rather
// than a template and leaves nothing for another language to be written
// beside.
//
// Named slots only, for that same reason. A hole whose meaning is its
// position cannot be moved, and two languages do not agree about position.
//
// Both kinds of hole throw rather than reaching the page. A sentence missing
// in the reader's language has no identifier to hand over the way a word
// does. And a slot nothing was given for prints as `{name}`: this file's
// half of the language had only the word half, so the one sentence here that
// had a hole filled it with a hand-written `replace`, where the name typed
// at the call site and the name in the text were two literals that had to
// happen to agree.
//
// A doubled brace is a brace and not a hole, which is the one rule this
// half of the language was missing. It cost nothing while every sentence
// here was hand-written, because nobody writing a sentence by hand writes
// `{{`; it started to matter when the kernel began generating these tables
// (#399), because from then on every construct the kernel's own renderer
// admits is one this file is handed. A sentence naming a Python call —
// `estimate(measurement_error={<name>: {error_variance}})` — is written
// with doubled braces at the source and reaches a reader with single ones,
// and a renderer that did not know that showed the reader a hole where the
// kernel showed them a brace.
const TOKEN = /\{\{|\}\}|\{(\w+)\}/g

// Every slot name a sentence has, in any language it is written in.
//
// The union rather than one language's, for the reason the kernel's twin
// of this gives: a hole one language names and another does not is a hole,
// and which languages have it is not the reader's problem. Here rather
// than at the one call site because the caller that asks what the holes
// ARE and the caller that FILLS them must agree about what a hole is —
// two regexes for that is two answers, and the one that read a doubled
// brace as a hole was the reason this is a function.
export function holes(words: Words): Set<string> {
  const found = new Set<string>()
  for (const text of Object.values(words)) {
    for (const [, name] of text.matchAll(TOKEN)) if (name) found.add(name)
  }
  return found
}

export function fill(
  words: Words,
  lang: Lang = DEFAULT_LANG,
  slots: Record<string, string | number> = {},
): string {
  const text = words[lang]
  if (text === undefined) {
    throw new Error(
      `no ${lang} text for this sentence; it exists in ` +
        `${Object.keys(words).sort().join(', ') || 'no language'}`,
    )
  }
  return text.replace(TOKEN, (whole, name?: string) => {
    if (name === undefined) return whole[0]
    if (!(name in slots)) {
      throw new Error(`this sentence has a {${name}} and nothing filled it`)
    }
    return String(slots[name])
  })
}

// What this surface puts where a fact should have been.
//
// Both rows used to be a bare backticked identifier on both surfaces —
// which is how this build writes a name the sentence is ABOUT, so an
// absence arrived wearing a presence's notation and three different things
// read alike.
//
// themis/language.py:ABSENT, restated. Not generated from the kernel like
// the twenty vocabularies are: that registry anchors every row on what an
// ENVELOPE may carry, and these are what a renderer puts where nothing was
// carried. They sit with the mechanism that uses them — `fill`, `say` and
// `holes` above are two hand-written copies too — and a gate holds the two
// tables equal, which for four strings is what generating would have bought.
const ABSENCE_WORDS: Record<string, Words> = {
  no_fact_for_this_slot: {
    zh: '（未提供 {name}）',
    en: '(no {name} given)',
  },
  no_word_for_this_token: {
    zh: '`{token}`（本版本没有它的说法）',
    en: '`{token}` (this build has no word for it)',
  },
}

export function absent(
  kind: 'no_fact_for_this_slot' | 'no_word_for_this_token',
  lang: Lang,
  slots: Record<string, string>,
): string {
  const words = ABSENCE_WORDS[kind]
  // The identifier this replaced, where the reader's language is one this
  // build has no words in at all — a marker is itself a sentence, and "there
  // is no word for this here" is not sayable in a language nothing here is
  // written in. The kernel's `absent` says the same thing the same way.
  if (!say(words, lang, '')) return `\`${slots.token ?? slots.name ?? ''}\``
  return fill(words, lang, slots)
}

// The reader's word for a value read back off an envelope.
//
// The same shape as the kernel's `gloss`, and the same three cases. A value
// with a word gets the word; a value with no word keeps its own token and
// says beside it that this build has no word for it; NO value gets the
// empty string, because whether an optional field's absence is worth a
// sentence belongs to the sentence around it. `unknown` is for a caller
// whose sentence needs a phrase neither of those would fit into — never
// for handing back the token, which is what this already does and what
// lets the stand-in say it is one.
export function gloss(
  table: Record<string, Words>,
  value: unknown,
  lang: Lang = DEFAULT_LANG,
  unknown?: string,
): string {
  if (value === null || value === undefined) return unknown ?? ''
  const token = String(value)
  return say(table[token], lang,
    unknown === undefined ? absent('no_word_for_this_token', lang, { token }) : unknown)
}
