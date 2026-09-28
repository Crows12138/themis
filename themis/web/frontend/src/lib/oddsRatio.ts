import type { Words } from './language'

// How to read an `OR(y=a | x=b/c)` row. Two surfaces show one — the numbers
// the AI gave, under review, and the form a reader types a table into — and
// it is one sentence, so it is written once.
export const HOW_AN_ODDS_RATIO_READS = {
  zh: '优势比 OR(y=甲 | x=乙/丙)：其他条件不变，x 取乙而不是丙时，y=甲 的优势（发生的概率 ÷ 不发生的概率）乘以这个数。1 是没有影响，大于 1 更容易发生，小于 1 更不容易。',
  en: 'An odds ratio OR(y=a | x=b/c): with the other conditions unchanged, x at b rather than c multiplies the odds of y=a (its probability ÷ the probability it does not happen) by this number. 1 is no effect, above 1 more likely, below 1 less likely.',
} satisfies Words
