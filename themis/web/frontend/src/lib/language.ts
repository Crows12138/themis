// Which language this surface is answering the reader in.
//
// The browser's half of `themis/language.py`. The kernel decides which
// languages exist; this decides which one the page is showing. A test pins
// LANGS below equal to `themis.language.Lang` — a language the kernel gains
// and the browser does not is a page that cannot show what the answer has,
// and one the browser gains alone is a page offering a choice with nothing
// behind it.
export const LANGS = ['zh'] as const

export type Lang = (typeof LANGS)[number]

// What a reader gets who has not chosen. The same default the kernel has,
// and for the same reason: it is the language every word here was written
// in first.
export const DEFAULT_LANG: Lang = 'zh'

// One thing's reader-facing text, by language. Partial because a hole is a
// thing that can happen to a build, and `say` is where it is answered.
export type Words = Partial<Record<string, string>>

// One thing's text in the reader's language, or `unknown`.
//
// Nothing falls back to another language. A page half in a language the
// reader did not ask for is the defect, not the fix — so a missing text
// reads as the identifier, which a reader can at least look up.
export function say(words: Words | undefined, lang: Lang, unknown: string): string {
  const said = words?.[lang]
  return said === undefined ? unknown : said
}
