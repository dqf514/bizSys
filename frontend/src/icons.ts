/**
 * 图标注册表（UI-B 包体瘦身）：只打包实际使用的 EP 图标，替代 @element-plus/icons-vue 全量注册。
 * 动态场景——后端菜单 icon 字段（seeds/init_data.py）、Dock/快捷方式、ActionBar/流程节点 icon 字符串——
 * 均经 resolveComponent 按名解析；新增图标名必须先在下方注册，否则渲染为空。
 */
import type { App, Component } from 'vue'
import {
  AlarmClock, ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Avatar,
  Back, Bell, Bottom, Box, Brush, Calendar,
  Camera, CircleCheck, CircleClose, CirclePlus, Close, Coin,
  Collection, Connection, CopyDocument, CreditCard, Cpu, DArrowLeft, DArrowRight,
  DataAnalysis, DataLine, Delete, Document, DocumentAdd, DocumentCopy,
  Download, Edit, EditPen, Expand, Files, FirstAidKit, Flag,
  Fold, FolderDelete, Goods, Grid, InfoFilled, Iphone, Key, Link,
  List, Lock, MagicStick, Memo, Menu, Money,
  Monitor, Moon, MoreFilled, Notebook, Odometer, OfficeBuilding, Open,
  Operation, PieChart, Plus, Position, Postcard, Promotion,
  Rank, RefreshLeft, Right, Search, Sell, Service,
  Setting, ShoppingCart, Stamp, Star, StarFilled, Suitcase,
  Sunny, Switch, SwitchButton, Tickets, Tools, Top, TrendCharts, TurnOff,
  Upload, User, UserFilled, View, Wallet, Warning, VideoPlay,
} from '@element-plus/icons-vue'

const registry: Record<string, Component> = {
  AlarmClock, ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Avatar,
  Back, Bell, Bottom, Box, Brush, Calendar,
  Camera, CircleCheck, CircleClose, CirclePlus, Close, Coin,
  Collection, Connection, CopyDocument, CreditCard, Cpu, DArrowLeft, DArrowRight,
  DataAnalysis, DataLine, Delete, Document, DocumentAdd, DocumentCopy,
  Download, Edit, EditPen, Expand, Files, FirstAidKit, Flag,
  Fold, FolderDelete, Goods, Grid, InfoFilled, Iphone, Key, Link,
  List, Lock, MagicStick, Memo, Menu, Money,
  Monitor, Moon, MoreFilled, Notebook, Odometer, OfficeBuilding, Open,
  Operation, PieChart, Plus, Position, Postcard, Promotion,
  Rank, RefreshLeft, Right, Search, Sell, Service,
  Setting, ShoppingCart, Stamp, Star, StarFilled, Suitcase,
  Sunny, Switch, SwitchButton, Tickets, Tools, Top, TrendCharts, TurnOff,
  Upload, User, UserFilled, View, Wallet, Warning, VideoPlay,
}

export function setupIcons(app: App) {
  for (const [name, comp] of Object.entries(registry)) app.component(name, comp)
}
