import { useSyncExternalStore } from 'react'
import { fetchOffers } from '../api'

// What this deployment offers, as the server declares it.
//
// Two facts. `llm`: whether there is a model behind this deployment.
// Three surfaces need one — asking in prose, the AI-priors fallback, and
// writing a result up as a reply — and everything else on this page is the
// kernel's, which holds no model. A roster of feature names would be a
// second place to forget an entry; what the three share is not a name.
// `visitor_key`: whether this page may ask the visitor for a key. A
// deployment that pays with its own has decided who pays, and a panel
// asking for the visitor's would contradict it.
//
// The page asks rather than assumes, because the server is the only side
// that knows, and it asks once: the answer is a fact about the
// deployment, not about the moment.
//
// `null` until the answer arrives, and it is not a third thing to draw.
// It means this page does not yet know which doors open, and a door
// nobody knows about is not drawn. Erring the other way would put a
// button on screen and then take it away.

export interface Offers {
  llm: boolean
  visitor_key: boolean
}

let offers: Offers | null = null
const listeners = new Set<() => void>()

function settle(next: Offers): void {
  offers = next
  for (const listener of listeners) listener()
}

// Failing to reach our own server is not evidence that a model is behind
// it, so the unreachable case settles the same way an absent one does.
// The cost of being wrong here is one hidden button on a page whose owner
// can look at the logs; the cost the other way is a button that spends a
// key nobody meant to spend.
void fetchOffers().then(settle, () => settle({ llm: false, visitor_key: false }))

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

// What THIS page may offer. A component asks; it does not import the
// answer — the same boundary `useLang` draws, and for the same reason.
export function useOffers(): Offers | null {
  return useSyncExternalStore(subscribe, () => offers)
}
