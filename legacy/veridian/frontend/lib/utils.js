'use client'

// Utility: pick status pill styles
export function getPillClass(action) {
  const map = {
    REFRAME:  'pill pill-amber',
    REROUTE:  'pill pill-purple',
    DEFER:    'pill pill-gray',
    OVERRIDE: 'pill pill-red',
    PROCEED:  'pill pill-green',
  }
  return map[action] ?? 'pill pill-gray'
}

// Utility: conflict type accent color (left bar on task card)
export function getAccentColor(task) {
  if (task?.security_flag)  return '#EF4444' // red
  if (task?.finance_flag)   return '#F59E0B' // amber
  if (task?.capacity_flag)  return '#7F77DD' // purple
  if (task?.hr_status && task.hr_status !== 'ACTIVE') return '#F59E0B'
  return '#22C55E' // green
}

// Utility: does a task have any flag?
export function hasFlag(task) {
  return !!(
    task?.security_flag ||
    task?.finance_flag ||
    task?.capacity_flag ||
    (task?.hr_status && task.hr_status !== 'ACTIVE' && task.hr_status !== 'NOT_FOUND' && task.hr_status !== 'QUERY_ERROR')
  )
}

// Utility: summarise conflict for display
export function getConflictLabel(task) {
  if (task?.security_flag)  return 'SECURITY'
  if (task?.finance_flag)   return 'BUDGET'
  if (task?.capacity_flag)  return 'CAPACITY'
  if (task?.hr_status && task.hr_status !== 'ACTIVE') return 'HR'
  return null
}

// Utility: format relative time
export function timeAgo(isoStr) {
  if (!isoStr) return ''
  const diff = (Date.now() - new Date(isoStr).getTime()) / 1000
  if (diff < 60) return `${Math.round(diff)}s ago`
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`
  return `${Math.round(diff / 86400)}d ago`
}

// Utility: assignee initials avatar
export function getInitials(name) {
  if (!name || name === 'UNASSIGNED') return '?'
  return name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2)
}
