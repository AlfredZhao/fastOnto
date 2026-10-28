import { Component, type ReactNode } from 'react';
export default class ErrorBoundary extends Component<{children: ReactNode}, {failed: boolean}> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? <main className="page"><h1>页面暂时无法显示</h1><p>请刷新重试；本地偏好损坏不会自动清除服务端模型。</p><button onClick={() => location.reload()}>刷新页面</button></main> : this.props.children; }
}
