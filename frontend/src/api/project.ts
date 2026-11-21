import { request, download, toQuery } from './http'
import type { ListQuery, PageResult, Project, ProjectGantt, ProjectTask } from './types'

/* ---------- 项目 ---------- */

export function listProjects(params: ListQuery) {
  return request<PageResult<Project>>({
    url: '/project/projects',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function projectCounts() {
  return request<Record<string, number>>({ url: '/project/projects/counts', method: 'get' })
}

export function getProject(id: number) {
  return request<Project & { gantt: ProjectGantt }>({
    url: `/project/projects/${id}`,
    method: 'get',
  })
}

export function createProject(data: Partial<Project>) {
  return request<Project>({ url: '/project/projects', method: 'post', data })
}

/** 基于合同立项（合同须已审批通过） */
export function createProjectFromContract(data: Partial<Project>) {
  return request<Project>({ url: '/project/projects/from-contract', method: 'post', data })
}

export function updateProject(id: number, data: Partial<Project>) {
  return request<Project>({ url: `/project/projects/${id}`, method: 'put', data })
}

export function deleteProject(id: number) {
  return request<void>({ url: `/project/projects/${id}`, method: 'delete' })
}

/* ---------- 项目任务（甘特行）---------- */

export function listProjectTasks(projectId: number) {
  return request<{ items: ProjectTask[]; total: number }>({
    url: `/project/projects/${projectId}/tasks`,
    method: 'get',
  })
}

export function createProjectTask(projectId: number, data: Partial<ProjectTask>) {
  return request<ProjectGantt>({
    url: `/project/projects/${projectId}/tasks`,
    method: 'post',
    data,
  })
}

export function updateProjectTask(id: number, data: Partial<ProjectTask>) {
  return request<ProjectGantt>({ url: `/project/project-tasks/${id}`, method: 'put', data })
}

export function deleteProjectTask(id: number) {
  return request<void>({ url: `/project/project-tasks/${id}`, method: 'delete' })
}

/** 从任务输入与已发布排期自动生成甘特 */
export function generateProjectTasks(
  projectId: number,
  data: { taskIds?: number[]; groupCode?: string; overwrite?: boolean },
) {
  return request<ProjectGantt>({
    url: `/project/projects/${projectId}/generate-tasks`,
    method: 'post',
    data,
  })
}

export function projectGantt(projectId: number) {
  return request<ProjectGantt>({ url: `/project/projects/${projectId}/gantt`, method: 'get' })
}

export function exportProjects(params: ListQuery) {
  return download(
    {
      url: '/project/projects/export',
      method: 'post',
      data: toQuery(params as Record<string, unknown>),
    },
    'projects.xlsx',
  )
}
