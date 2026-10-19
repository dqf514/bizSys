/** LogicFlow 自定义节点注册：start/approval/condition/cc/end，颜色取自 bizSys 设计令牌。
 *
 * SVG presentation attribute 不支持 var()，LogicFlow 主题/style 对象最终落在 attribute 上，
 * 因此这里在取样式时用 getComputedStyle 解析令牌为字面色值（暗色主题切换后重绘即生效）。
 */
import { CircleNode, CircleNodeModel, RectNode, RectNodeModel, h } from '@logicflow/core'

export function resolveToken(name: string, fallback: string): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || fallback
}

function typeStyle(nodeType: string): { fill: string; stroke: string } {
  switch (nodeType) {
    case 'condition':
      return {
        fill: resolveToken('--bs-color-semantic-warning-soft', '#fffbeb'),
        stroke: resolveToken('--bs-color-semantic-warning', '#d97706'),
      }
    case 'cc':
      return {
        fill: resolveToken('--bs-color-fill-light', '#f5f6f8'),
        stroke: resolveToken('--bs-color-accent-cyan', '#0891b2'),
      }
    default:
      return {
        fill: resolveToken('--bs-color-semantic-info-soft', '#eff6ff'),
        stroke: resolveToken('--bs-color-semantic-info', '#2563eb'),
      }
  }
}

/** 由 viewer/designer 在 render 前注入当前节点序号集合，用于高亮 */
export const highlightSeqs: Set<number> = new Set()

class FlowRectModel extends RectNodeModel {
  initNodeData(data: Parameters<RectNodeModel['initNodeData']>[0]) {
    super.initNodeData(data)
    this.width = 180
    this.height = 64
    this.radius = 8
  }

  getNodeStyle() {
    const style = super.getNodeStyle()
    const meta = typeStyle(this.getNodeType())
    style.fill = meta.fill
    style.stroke = meta.stroke
    style.strokeWidth = 1.5
    const seq = Number(this.properties?.seq)
    if (highlightSeqs.size && highlightSeqs.has(seq)) {
      style.stroke = resolveToken('--bs-color-primary', '#2563eb')
      style.strokeWidth = 3
    }
    return style
  }

  getTextStyle() {
    const style = super.getTextStyle()
    style.fontSize = 13
    style.color = resolveToken('--bs-color-fg-default', '#1f2329')
    return style
  }

  getNodeType(): string {
    return (this.properties?.nodeType as string) || 'approval'
  }
}

class FlowRectView extends RectNode {
  getShape() {
    const { model } = this.props
    const { x, y, width, height, radius } = model
    const style = model.getNodeStyle()
    const name = String(model.properties?.nodeName ?? '')
    const subtitle = String(model.properties?.subtitle ?? '')
    return h('g', {}, [
      h('rect', {
        ...style,
        x: x - width / 2,
        y: y - height / 2,
        width,
        height,
        rx: radius,
        ry: radius,
      }),
      h(
        'text',
        {
          x,
          y: subtitle ? y - 8 : y,
          fill: resolveToken('--bs-color-fg-default', '#1f2329'),
          fontSize: 13,
          fontWeight: 600,
          textAnchor: 'middle',
          dominantBaseline: 'middle',
        },
        name,
      ),
      subtitle
        ? h(
            'text',
            {
              x,
              y: y + 14,
              fill: resolveToken('--bs-color-fg-muted', '#8a94a3'),
              fontSize: 11,
              textAnchor: 'middle',
              dominantBaseline: 'middle',
            },
            subtitle,
          )
        : null,
    ])
  }
}

class FlowCircleModel extends CircleNodeModel {
  initNodeData(data: Parameters<CircleNodeModel['initNodeData']>[0]) {
    super.initNodeData(data)
    this.r = 26
  }

  getNodeStyle() {
    const style = super.getNodeStyle()
    if ((this as { type: string }).type === 'start') {
      style.fill = resolveToken('--bs-color-semantic-success-soft', '#ecfdf3')
      style.stroke = resolveToken('--bs-color-semantic-success', '#16a34a')
    } else {
      style.fill = resolveToken('--bs-color-fill-light', '#f5f6f8')
      style.stroke = resolveToken('--bs-color-fg-muted', '#8a94a3')
    }
    style.strokeWidth = 1.5
    return style
  }
}

class StartView extends CircleNode {}
class EndView extends CircleNode {}

export function registerFlowNodes(lf: { register: (arg: { type: string; view: never; model: never }) => void }) {
  lf.register({ type: 'approval', view: FlowRectView as never, model: FlowRectModel as never })
  lf.register({ type: 'condition', view: FlowRectView as never, model: FlowRectModel as never })
  lf.register({ type: 'cc', view: FlowRectView as never, model: FlowRectModel as never })
  lf.register({ type: 'start', view: StartView as never, model: FlowCircleModel as never })
  lf.register({ type: 'end', view: EndView as never, model: FlowCircleModel as never })
}
