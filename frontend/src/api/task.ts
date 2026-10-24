import { request, download, toQuery } from './http'
import type {
  ListQuery,
  PageResult,
  SampleRow,
  Task,
  TaskCounts,
  TaskItem,
  TaskSample,
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
  return request<void>({ url: `/task/samples/${sampleId}/${action}`, method: 'post' })
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
