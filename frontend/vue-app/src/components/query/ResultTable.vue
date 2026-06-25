<template>
  <div v-if="columns.length && results.length" class="border border-grid bg-surface rounded shadow-card overflow-hidden">
    <div class="h-8 hairline-b flex items-center justify-between px-4">
      <span class="font-mono text-[10px] uppercase text-primary/40 tracking-wider">
        查询结果 <span class="text-accent-green font-bold ml-1">{{ totalCount ? '共 ' + totalCount.toLocaleString() + ' 条' : '' }}</span>
      </span>
    </div>
    <div class="overflow-x-auto">
      <table class="w-full text-left">
        <thead>
          <tr class="border-b border-grid bg-warm-gray">
            <th
              v-for="col in columns"
              :key="col"
              class="px-4 py-2.5 font-mono text-[11px] font-bold text-primary/60 uppercase tracking-wider whitespace-nowrap"
            >{{ col }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, i) in results"
            :key="i"
            class="border-b border-grid last:border-0"
            :class="i % 2 === 0 ? 'bg-surface' : 'bg-warm-gray/50'"
          >
            <td
              v-for="col in columns"
              :key="col"
              class="px-4 py-2.5 text-[13px] whitespace-nowrap"
              :class="isNumericCell(row[col]) ? 'font-mono text-right font-medium' : 'text-primary/80'"
            >{{ formatCell(row[col]) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
defineProps({
  columns: { type: Array, default: () => [] },
  results: { type: Array, default: () => [] },
  totalCount: { type: Number, default: 0 },
})

function formatCell(val) {
  if (val === null || val === undefined) return '—'
  if (typeof val === 'number') return val.toLocaleString()
  return String(val)
}

function isNumericCell(val) {
  if (val === null || val === undefined) return false
  if (typeof val === 'number') return true
  if (typeof val === 'string' && /^\d{4}-\d{2}-\d{2}/.test(val)) return false
  const parsed = parseFloat(String(val).replace(/,/g, ''))
  return !isNaN(parsed) && isFinite(parsed)
}
</script>
