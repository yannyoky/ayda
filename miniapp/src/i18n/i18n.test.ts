import { formatNumber, plural } from '.'

describe('plural', () => {
  it.each([
    [1, 'день'],
    [2, 'дня'],
    [5, 'дней'],
    [11, 'дней'],
    [12, 'дней'],
    [21, 'день'],
    [22, 'дня'],
    [111, 'дней'],
  ])('%i → %s', (n, form) => {
    expect(plural(n, ['день', 'дня', 'дней'])).toBe(form)
  })
})

it('formats thousands with a Russian separator', () => {
  expect(formatNumber(1240).replace(/\s/g, ' ')).toBe('1 240')
})
