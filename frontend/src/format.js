const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })
const number = new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 })

export const formatMoney = (value) => usd.format(value)
export const formatNumber = (value) => number.format(value)
export const formatPrice = (value) => `$${value.toFixed(3)}`

export function formatDuration(seconds) {
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.round((seconds % 3600) / 60)
  return hours ? `${hours} h ${minutes} min` : `${minutes} min`
}
