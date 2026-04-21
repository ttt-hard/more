import React from "react";

type Props = {
  children: React.ReactNode;
};

type State = {
  error: Error | null;
};

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    // eslint-disable-next-line no-console
    console.error("[ErrorBoundary] Uncaught render error", error, info);
  }

  handleReset = () => {
    this.setState({ error: null });
  };

  render() {
    if (this.state.error) {
      return (
        <div className="error-boundary-shell">
          <div className="error-boundary-card">
            <div className="error-boundary-kicker">界面渲染异常</div>
            <div className="error-boundary-title">助手界面遇到一个错误</div>
            <div className="error-boundary-copy">
              {this.state.error.message || "发生未知渲染错误。"}
            </div>
            <pre className="error-boundary-stack">
              {this.state.error.stack?.split("\n").slice(0, 6).join("\n")}
            </pre>
            <div className="error-boundary-actions">
              <button className="compact-button compact-button-strong" onClick={this.handleReset}>
                返回界面
              </button>
              <button
                className="compact-button compact-button-muted"
                onClick={() => {
                  if (typeof window !== "undefined") {
                    window.location.reload();
                  }
                }}
              >
                重新加载
              </button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
