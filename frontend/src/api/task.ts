import { request, download, toQuery } from './http'
import type {
  ListQuery,
  OperationFlow,
  PageResult,
  SampleRow,
  Task,
  TaskAssignment,
  TaskCounts,
  TaskItem,
  TaskProcess,
  TaskSample,
  TaskTrace,
} from './types'

export function listTasks(params: ListQuery) {
  return request<PageResult<Task>>({
    url: '/task/tasks',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function taskCounts() {
  return request<TaskCounts>({ url: '/task/tasks/counts', method: 'get' })
}

export function getTask(id: number) {
  return request<Task>({ url: `/task/tasks/${id}`, method: 'get' })
}

export function createTask(data: Partial<Task>) {
  return request<Task>({ url: '/task/tasks', method: 'post', data })
}

export function updateTask(id: number, data: Partial<Task>) {
  return request<Task>({ url: `/task/tasks/${id}`, method: 'put', data })
}

export function deleteTask(id: number) {
  return request<void>({ url: `/task/tasks/${id}`, method: 'delete' })
}

export type TaskAction = 'submit' | 'finish' | 'stop'

export function taskAction(id: number, action: TaskAction) {
  return request<void>({ url: `/task/tasks/${id}/${action}`, method: 'post' })
}

export function addTaskItem(taskId: number, data: Partial<TaskItem>) {
  return request<TaskItem>({ url: `/task/tasks/${taskId}/items`, method: 'post', data })
}

export function updateTaskItem(itemId: number, data: Partial<TaskItem>) {
  return request<TaskItem>({ url: `/task/items/${itemId}`, method: 'put', data })
}

export function deleteTaskItem(itemId: number) {
  return request<void>({ url: `/task/items/${itemId}`, method: 'delete' })
}

export function addTaskSample(taskId: number, data: Partial<TaskSample>) {
  return request<TaskSample>({ url: `/task/tasks/${taskId}/samples`, method: 'post', data })
}

export function updateTaskSample(sampleId: number, data: Partial<TaskSample>) {
  return request<TaskSample>({ url: `/task/samples/${sampleId}`, method: 'put', data })
}

export function deleteTaskSample(sampleId: number) {
  return request<void>({ url: `/task/samples/${sampleId}`, method: 'delete' })
}

export function sampleFlow(sampleId: number, action: 'in' | 'out') {
  return request<TaskSample>({ url: `/task/samples/${sampleId}/${action}`, method: 'post' })
}

export function cancelSampleStock(sampleId: number) {
  return request<TaskSample>({ url: `/task/samples/${sampleId}/stock-cancel`, method: 'post' })
}

export function listSamples(params: ListQuery) {
  return request<PageResult<SampleRow>>({
    url: '/task/samples',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function sampleCounts() {
  return request<Record<string, number>>({ url: '/task/samples/counts', method: 'get' })
}

export function exportSamples(params: ListQuery) {
  return download(
    {
      url: '/task/samples/export',
      method: 'post',
      data: toQuery(params as Record<string, unknown>),
    },
    'samples.xlsx',
  )
}

export function exportTasks(params: ListQuery) {
  return download(
    {
      url: '/task/tasks/export',
      method: 'post',
      data: toQuery(params as Record<string, unknown>),
    },
    'tasks.xlsx',
  )
}

/* ---------- B5 工序流转 ---------- */

export function listProcesses(taskId: number) {
  return request<{ items: TaskProcess[]; total: number }>({
    url: `/task/tasks/${taskId}/processes`,
    method: 'get',
  })
}

export function createProcess(taskId: number, data: Partial<TaskProcess>) {
  return request<TaskProcess>({
    url: `/task/tasks/${taskId}/processes`,
    method: 'post',
    data,
  })
}

export function updateProcess(id: number, data: Partial<TaskProcess>) {
  return request<TaskProcess>({ url: `/task/processes/${id}`, method: 'put', data })
}

export function startProcess(id: number) {
  return request<TaskProcess>({ url: `/task/processes/${id}/start`, method: 'post' })
}

export function finishProcess(id: number) {
  return request<TaskProcess>({ url: `/task/processes/${id}/finish`, method: 'post' })
}

export function skipProcess(id: number) {
  return request<TaskProcess>({ url: `/task/processes/${id}/skip`, method: 'post' })
}

export function deleteProcess(id: number) {
  return request<void>({ url: `/task/processes/${id}`, method: 'delete' })
}

/* ---------- B5 七维分配 ---------- */

export function listAssignments(taskId: number) {
  return request<{ items: TaskAssignment[]; total: number }>({
    url: `/task/tasks/${taskId}/assignments`,
    method: 'get',
  })
}

export function createAssignment(taskId: number, data: Partial<TaskAssignment>) {
  return request<TaskAssignment>({
    url: `/task/tasks/${taskId}/assignments`,
    method: 'post',
    data,
  })
}

export function updateAssignment(id: number, data: Partial<TaskAssignment>) {
  return request<TaskAssignment>({ url: `/task/assignments/${id}`, method: 'put', data })
}

export function deleteAssignment(id: number) {
  return request<void>({ url: `/task/assignments/${id}`, method: 'delete' })
}

/* ---------- B5 全过程追溯 ---------- */

export function listTraces(taskId: number) {
  return request<{ items: TaskTrace[]; total: number }>({
    url: `/task/tasks/${taskId}/traces`,
    method: 'get',
  })
}

export function createTrace(taskId: number, data: Partial<TaskTrace>) {
  return request<TaskTrace>({ url: `/task/tasks/${taskId}/traces`, method: 'post', data })
}

export function deleteTrace(id: number) {
  return request<void>({ url: `/task/traces/${id}`, method: 'delete' })
}

/* ---------- B5 操作流程图 / 负责人建议 ---------- */

export function operationFlow(taskId: number) {
  return request<OperationFlow>({ url: `/task/tasks/${taskId}/operation-flow`, method: 'get' })
}

export function ownerSuggestion(taskId: number) {
  return request<{
    taskId: number
    taskType: string
    roleGroup: string
    roleGroupText: string
    ownerId: number | null
    ownerName: string
  }>({ url: `/task/tasks/${taskId}/owner-suggestion`, method: 'get' })
}
