const maxFen = 2_147_483_647

export function readYuan(value: string): number | undefined {
  const match = /^(\d+)(?:\.(\d{1,2}))?$/.exec(value.trim())
  if (!match) return undefined
  const fen = Number(match[1]) * 100 + Number((match[2] ?? '').padEnd(2, '0'))
  return Number.isSafeInteger(fen) && fen <= maxFen ? fen : undefined
}

export function formatYuan(fen: number | null | undefined) {
  return fen == null ? '—' : `¥${(fen / 100).toFixed(2)}`
}
