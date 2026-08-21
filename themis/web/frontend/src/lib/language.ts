// Which language this surface is answering the reader in.
//
// The browser's half of `themis/language.py`, mirroring its two sets and its
// one lookup. A test pins both sets equal to the kernel's — a language the
// kernel gains and the browser does not is a page that cannot show what the
// answer has, and one the browser gains alone is a page offering a choice
// with nothing behind it.

// Answered in. What a chooser may offer, and what the kernel's `Lang` holds.
export const LANGS = ['zh'] as const

// Being written, and not yet offered. Words keyed by one of these are legal
// and are held to the same completeness as any other — what is not yet true
// of them is that every surface has been reached, and a page that offered a
// half-reached language would hand a reader half of another one.
export const ARRIVING = [] as const

export type Lang = (typeof LANGS)[number] | (typeof ARRIVING)[number]

// Every language some text here is written in: the denominator of the
// completeness check, which is a wider question than what may be offered.
export const WRITTEN: readonly Lang[] = [...LANGS, ...ARRIVING]

// What a reader gets who has not chosen. The same default the kernel has,
// and for the same reason: it is the language every word here was written
// in first.
export const DEFAULT_LANG: Lang = 'zh'

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

// The reader's word for a value read back off an envelope.
//
// The same shape as the kernel's `gloss`: an unlisted value renders as its
// own token rather than as silence or a guess, and a value this build has
// never heard of reads the same as one it cannot say in this language —
// stated here so nobody reads the shared fallback as one fact.
export function gloss(
  table: Record<string, Words>,
  value: unknown,
  lang: Lang = DEFAULT_LANG,
  unknown?: string,
): string {
  const token = String(value ?? '')
  return say(table[token], lang, unknown === undefined ? `\`${token}\`` : unknown)
}
